package service

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestHashPassword_And_Verify(t *testing.T) {
	svc := &AuthService{}

	hash, err := svc.HashPassword("testpassword123")
	require.NoError(t, err)
	assert.NotEmpty(t, hash)
	assert.NotEqual(t, "testpassword123", hash)

	assert.True(t, svc.VerifyPassword(hash, "testpassword123"))
	assert.False(t, svc.VerifyPassword(hash, "wrongpassword"))
}

func TestCreateAccessToken(t *testing.T) {
	svc := NewAuthService(nil, []string{"test-key-32-chars-minimum-length"}, "HS256", 15, 7)

	token, expiresIn, err := svc.CreateAccessToken("user123")
	require.NoError(t, err)
	assert.NotEmpty(t, token)
	assert.Equal(t, 900, expiresIn)
}

func TestCreateRefreshToken(t *testing.T) {
	svc := NewAuthService(nil, []string{"test-key-32-chars-minimum-length"}, "HS256", 15, 7)

	token, jti, expiresAt, err := svc.CreateRefreshToken("user123")
	require.NoError(t, err)
	assert.NotEmpty(t, token)
	assert.NotEmpty(t, jti)
	assert.False(t, expiresAt.IsZero())
}

func TestValidateRefreshToken_Valid(t *testing.T) {
	svc := NewAuthService(nil, []string{"test-key-32-chars-minimum-length"}, "HS256", 15, 7)

	tokenStr, _, _, err := svc.CreateRefreshToken("user123")
	require.NoError(t, err)

	claims, err := svc.ValidateRefreshToken(tokenStr)
	require.NoError(t, err)
	assert.Equal(t, "user123", claims["sub"])
	assert.Equal(t, "refresh", claims["type"])
}

func TestValidateRefreshToken_AccessTokenRejected(t *testing.T) {
	svc := NewAuthService(nil, []string{"test-key-32-chars-minimum-length"}, "HS256", 15, 7)

	tokenStr, _, err := svc.CreateAccessToken("user123")
	require.NoError(t, err)

	_, err = svc.ValidateRefreshToken(tokenStr)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "not a refresh token")
}

func TestValidateRefreshToken_WrongKey(t *testing.T) {
	svc1 := NewAuthService(nil, []string{"key-one-is-32-chars-long-minimum"}, "HS256", 15, 7)
	svc2 := NewAuthService(nil, []string{"key-two-is-32-chars-long-minimum"}, "HS256", 15, 7)

	tokenStr, _, _, err := svc1.CreateRefreshToken("user123")
	require.NoError(t, err)

	_, err = svc2.ValidateRefreshToken(tokenStr)
	require.Error(t, err)
}

func TestValidateRefreshToken_KeyRotation(t *testing.T) {
	oldKey := "old-key-is-32-chars-long-minimum"
	newKey := "new-key-is-32-chars-long-minimum"

	svcOld := NewAuthService(nil, []string{oldKey}, "HS256", 15, 7)
	svcNew := NewAuthService(nil, []string{newKey, oldKey}, "HS256", 15, 7)

	tokenStr, _, _, err := svcOld.CreateRefreshToken("user123")
	require.NoError(t, err)

	claims, err := svcNew.ValidateRefreshToken(tokenStr)
	require.NoError(t, err)
	assert.Equal(t, "user123", claims["sub"])
}

func TestGenerateCSRFToken(t *testing.T) {
	token1 := GenerateCSRFToken()
	token2 := GenerateCSRFToken()
	assert.NotEmpty(t, token1)
	assert.NotEqual(t, token1, token2)
}

func TestValidateCSRF(t *testing.T) {
	assert.True(t, ValidateCSRF("token123", "token123"))
	assert.True(t, ValidateCSRF("token123 ", " token123"))
	assert.False(t, ValidateCSRF("", "token123"))
	assert.False(t, ValidateCSRF("token123", ""))
	assert.False(t, ValidateCSRF("token1", "token2"))
}

func TestExtractIPSubnet_IPv4(t *testing.T) {
	subnet := extractIPSubnet("192.168.1.100:8080")
	assert.Equal(t, "192.168.1.0/24", subnet)
}

func TestExtractIPSubnet_IPv6(t *testing.T) {
	subnet := extractIPSubnet("[2001:db8::1]:8080")
	assert.Equal(t, "2001:db8::/64", subnet)
}

func TestExtractIPSubnet_Invalid(t *testing.T) {
	subnet := extractIPSubnet("invalid")
	assert.Equal(t, "invalid", subnet)
}

func TestHashUserAgent(t *testing.T) {
	hash1 := hashUserAgent("Mozilla/5.0")
	hash2 := hashUserAgent("Mozilla/5.0")
	hash3 := hashUserAgent("Chrome/91")

	assert.Equal(t, hash1, hash2)
	assert.NotEqual(t, hash1, hash3)
	assert.Len(t, hash1, 64) // SHA256 hex
}
