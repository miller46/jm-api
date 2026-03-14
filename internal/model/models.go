package model

import (
	"crypto/rand"
	"math/big"
	"time"
)

const idChars = "abcdefghijklmnopqrstuvwxyz0123456789"
const idLength = 32

func GenerateID() string {
	b := make([]byte, idLength)
	for i := range b {
		n, _ := rand.Int(rand.Reader, big.NewInt(int64(len(idChars))))
		b[i] = idChars[n.Int64()]
	}
	return string(b)
}

// Supported webhook event types
var SupportedEventTypes = []string{
	"bot.created",
	"bot.updated",
	"bot.deleted",
	"bot.ran",
}

func IsValidEventType(et string) bool {
	for _, t := range SupportedEventTypes {
		if t == et {
			return true
		}
	}
	return false
}

// Response types

type UserResponse struct {
	ID       string `json:"id"`
	Email    string `json:"email"`
	IsActive bool   `json:"is_active"`
	IsAdmin  bool   `json:"is_admin"`
}

type TokenResponse struct {
	AccessToken string `json:"access_token"`
	TokenType   string `json:"token_type"`
	ExpiresIn   int    `json:"expires_in"`
}

type SessionInfo struct {
	TokenJTI  string     `json:"token_jti"`
	IssuedAt  time.Time  `json:"issued_at"`
	ExpiresAt time.Time  `json:"expires_at"`
	RevokedAt *time.Time `json:"revoked_at,omitempty"`
	Current   bool       `json:"current"`
}

type SessionListResponse struct {
	Sessions []SessionInfo `json:"sessions"`
}

type BotResponse struct {
	ID           string     `json:"id"`
	RigID        string     `json:"rig_id"`
	LastRunAt    *time.Time `json:"last_run_at"`
	KillSwitch   bool       `json:"kill_switch"`
	LastRunLog   *string    `json:"last_run_log"`
	CreateAt     time.Time  `json:"create_at"`
	LastUpdateAt time.Time  `json:"last_update_at"`
}

type BotListResponse struct {
	Items   []BotResponse `json:"items"`
	Total   int64         `json:"total"`
	Page    int           `json:"page"`
	PerPage int           `json:"per_page"`
	Pages   int           `json:"pages"`
}

type WebhookResponse struct {
	ID           string    `json:"id"`
	UserID       string    `json:"user_id"`
	TargetURL    string    `json:"target_url"`
	EventTypes   []string  `json:"event_types"`
	IsActive     bool      `json:"is_active"`
	CreateAt     time.Time `json:"create_at"`
	LastUpdateAt time.Time `json:"last_update_at"`
}

type WebhookDeliveryLogResponse struct {
	ID           string     `json:"id"`
	WebhookID    string     `json:"webhook_id"`
	EventID      string     `json:"event_id"`
	EventType    string     `json:"event_type"`
	Success      bool       `json:"success"`
	Attempts     int        `json:"attempts"`
	StatusCode   *int32     `json:"status_code"`
	ResponseBody *string    `json:"response_body"`
	ErrorMessage *string    `json:"error_message"`
	CreateAt     time.Time  `json:"create_at"`
}

type TaskResponse struct {
	ID          string          `json:"id"`
	Type        string          `json:"type"`
	Status      string          `json:"status"`
	Payload     interface{}     `json:"payload,omitempty"`
	Result      interface{}     `json:"result,omitempty"`
	Error       *string         `json:"error,omitempty"`
	RetryCount  int             `json:"retry_count"`
	CreatedAt   time.Time       `json:"created_at"`
	CompletedAt *time.Time      `json:"completed_at,omitempty"`
}

type MetaResponse struct {
	Version     string `json:"version"`
	GitSHA      string `json:"git_sha"`
	DeployedAt  string `json:"deployed_at"`
	Environment string `json:"environment"`
}

type ErrorResponse struct {
	Error string `json:"error"`
}

type MessageResponse struct {
	Status string `json:"status"`
}
