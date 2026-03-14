package service

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"net"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/model"
	"golang.org/x/crypto/bcrypt"
)

type AuthService struct {
	queries              *sqlc.Queries
	signingKeys          []string
	algorithm            string
	accessTokenExpireMin int
	refreshTokenExpDays  int
}

func NewAuthService(q *sqlc.Queries, signingKeys []string, algorithm string, accessExpMin, refreshExpDays int) *AuthService {
	return &AuthService{
		queries:              q,
		signingKeys:          signingKeys,
		algorithm:            algorithm,
		accessTokenExpireMin: accessExpMin,
		refreshTokenExpDays:  refreshExpDays,
	}
}

type AccessTokenOption func(claims jwt.MapClaims)

func WithUserClaims(email string, isAdmin bool) AccessTokenOption {
	return func(claims jwt.MapClaims) {
		claims["email"] = email
		claims["is_admin"] = isAdmin
	}
}

func (s *AuthService) HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), 12)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}

func (s *AuthService) VerifyPassword(hash, password string) bool {
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(password)) == nil
}

func (s *AuthService) CreateAccessToken(userID string, opts ...AccessTokenOption) (string, int, error) {
	expiresIn := s.accessTokenExpireMin * 60
	now := time.Now()
	claims := jwt.MapClaims{
		"sub":  userID,
		"type": "access",
		"iat":  now.Unix(),
		"exp":  now.Add(time.Duration(s.accessTokenExpireMin) * time.Minute).Unix(),
	}
	for _, opt := range opts {
		opt(claims)
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenStr, err := token.SignedString([]byte(s.signingKeys[0]))
	if err != nil {
		return "", 0, err
	}
	return tokenStr, expiresIn, nil
}

func (s *AuthService) CreateRefreshToken(userID string) (string, string, time.Time, error) {
	jti := uuid.New().String()
	now := time.Now()
	expiresAt := now.Add(time.Duration(s.refreshTokenExpDays) * 24 * time.Hour)

	claims := jwt.MapClaims{
		"sub":  userID,
		"type": "refresh",
		"jti":  jti,
		"iat":  now.Unix(),
		"exp":  expiresAt.Unix(),
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenStr, err := token.SignedString([]byte(s.signingKeys[0]))
	if err != nil {
		return "", "", time.Time{}, err
	}
	return tokenStr, jti, expiresAt, nil
}

func (s *AuthService) ValidateRefreshToken(tokenStr string) (jwt.MapClaims, error) {
	var lastErr error
	for _, key := range s.signingKeys {
		token, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrSignatureInvalid
			}
			return []byte(key), nil
		})
		if err != nil {
			lastErr = err
			continue
		}
		if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
			tokenType, _ := claims["type"].(string)
			if tokenType != "refresh" {
				return nil, fmt.Errorf("not a refresh token")
			}
			return claims, nil
		}
	}
	return nil, lastErr
}

func (s *AuthService) PersistRefreshToken(ctx context.Context, jti, userID string, expiresAt time.Time, userAgent, remoteAddr string) error {
	uaHash := hashUserAgent(userAgent)
	subnet := extractIPSubnet(remoteAddr)

	_, err := s.queries.CreateSessionToken(ctx, sqlc.CreateSessionTokenParams{
		TokenJti:      jti,
		UserID:        userID,
		IssuedAt:      time.Now(),
		ExpiresAt:     expiresAt,
		UserAgentHash: pgtype.Text{String: uaHash, Valid: true},
		IpSubnet:      pgtype.Text{String: subnet, Valid: true},
	})
	return err
}

func (s *AuthService) GetRefreshTokenState(ctx context.Context, jti string) (string, error) {
	session, err := s.queries.GetSessionToken(ctx, jti)
	if err != nil {
		return "unknown", err
	}

	if session.RevokedAt != nil {
		return "revoked", nil
	}
	if session.ExpiresAt.Before(time.Now()) {
		return "expired", nil
	}
	return "active", nil
}

func (s *AuthService) RotateRefreshToken(ctx context.Context, oldJTI, userID, userAgent, remoteAddr string) (string, string, time.Time, error) {
	// Revoke old token
	if err := s.queries.RevokeSessionToken(ctx, oldJTI); err != nil {
		return "", "", time.Time{}, fmt.Errorf("revoking old token: %w", err)
	}

	// Create new refresh token
	tokenStr, newJTI, expiresAt, err := s.CreateRefreshToken(userID)
	if err != nil {
		return "", "", time.Time{}, err
	}

	uaHash := hashUserAgent(userAgent)
	subnet := extractIPSubnet(remoteAddr)

	_, err = s.queries.CreateSessionToken(ctx, sqlc.CreateSessionTokenParams{
		TokenJti:       newJTI,
		UserID:         userID,
		IssuedAt:       time.Now(),
		ExpiresAt:      expiresAt,
		RotatedFromJti: pgtype.Text{String: oldJTI, Valid: true},
		UserAgentHash:  pgtype.Text{String: uaHash, Valid: true},
		IpSubnet:       pgtype.Text{String: subnet, Valid: true},
	})
	if err != nil {
		return "", "", time.Time{}, fmt.Errorf("persisting new token: %w", err)
	}

	return tokenStr, newJTI, expiresAt, nil
}

func (s *AuthService) GetSession(ctx context.Context, jti string) (*sqlc.SessionToken, error) {
	session, err := s.queries.GetSessionToken(ctx, jti)
	if err != nil {
		return nil, err
	}
	return &session, nil
}

func (s *AuthService) RevokeSession(ctx context.Context, jti string) error {
	return s.queries.RevokeSessionToken(ctx, jti)
}

func (s *AuthService) RevokeAllUserSessions(ctx context.Context, userID string) error {
	return s.queries.RevokeAllUserSessionsUnconditional(ctx, userID)
}

func (s *AuthService) RevokeOtherSessions(ctx context.Context, userID, currentJTI string) (int64, error) {
	return s.queries.RevokeAllUserSessions(ctx, sqlc.RevokeAllUserSessionsParams{
		UserID:   userID,
		TokenJti: currentJTI,
	})
}

func (s *AuthService) ListUserSessions(ctx context.Context, userID string) ([]sqlc.SessionToken, error) {
	return s.queries.ListUserSessions(ctx, userID)
}

func (s *AuthService) Signup(ctx context.Context, email, password string) (*sqlc.User, error) {
	hash, err := s.HashPassword(password)
	if err != nil {
		return nil, err
	}

	user, err := s.queries.CreateUser(ctx, sqlc.CreateUserParams{
		ID:           model.GenerateID(),
		Email:        email,
		PasswordHash: hash,
		IsActive:     true,
		IsAdmin:      false,
	})
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func (s *AuthService) Login(ctx context.Context, email, password string) (*sqlc.User, error) {
	user, err := s.queries.GetUserByEmail(ctx, email)
	if err != nil {
		return nil, fmt.Errorf("invalid credentials")
	}

	if !s.VerifyPassword(user.PasswordHash, password) {
		return nil, fmt.Errorf("invalid credentials")
	}

	if !user.IsActive {
		return nil, fmt.Errorf("account is disabled")
	}

	return &user, nil
}

func GenerateCSRFToken() string {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		panic("crypto/rand failed: " + err.Error())
	}
	return base64.URLEncoding.EncodeToString(b)
}

func hashUserAgent(ua string) string {
	h := sha256.Sum256([]byte(ua))
	return hex.EncodeToString(h[:])
}

func extractIPSubnet(addr string) string {
	host := addr
	if h, _, err := net.SplitHostPort(addr); err == nil {
		host = h
	}
	ip := net.ParseIP(host)
	if ip == nil {
		return addr
	}
	if ip.To4() != nil {
		// IPv4: /24
		mask := net.CIDRMask(24, 32)
		return ip.Mask(mask).String() + "/24"
	}
	// IPv6: /64
	mask := net.CIDRMask(64, 128)
	return ip.Mask(mask).String() + "/64"
}

func (s *AuthService) DetectReplay(ctx context.Context, jti, userID string) (bool, error) {
	state, err := s.GetRefreshTokenState(ctx, jti)
	if err != nil {
		return false, err
	}
	if state == "revoked" {
		// Token reuse detected — revoke ALL sessions for this user
		if err := s.RevokeAllUserSessions(ctx, userID); err != nil {
			return true, err
		}
		return true, nil
	}
	return false, nil
}

func (s *AuthService) GetUserByID(ctx context.Context, userID string) (*sqlc.User, error) {
	user, err := s.queries.GetUserByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func (s *AuthService) CleanupExpiredSessions(ctx context.Context) error {
	return s.queries.CleanupExpiredSessions(ctx)
}

// EnrichAuthUser loads full user details from DB and populates the middleware auth user
func (s *AuthService) EnrichAuthUser(ctx context.Context, userID string) (*sqlc.User, error) {
	return s.GetUserByID(ctx, userID)
}

// ValidateCSRF checks that CSRF cookie matches header
func ValidateCSRF(cookieVal, headerVal string) bool {
	a := strings.TrimSpace(cookieVal)
	b := strings.TrimSpace(headerVal)
	return a != "" && b != "" && subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}
