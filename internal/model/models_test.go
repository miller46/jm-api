package model

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGenerateID_Length(t *testing.T) {
	id := GenerateID()
	assert.Len(t, id, 32)
}

func TestGenerateID_Unique(t *testing.T) {
	ids := make(map[string]bool)
	for i := 0; i < 100; i++ {
		id := GenerateID()
		assert.False(t, ids[id], "duplicate ID generated")
		ids[id] = true
	}
}

func TestGenerateID_ValidChars(t *testing.T) {
	id := GenerateID()
	for _, c := range id {
		assert.True(t, (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'), "invalid char: %c", c)
	}
}

func TestIsValidEventType(t *testing.T) {
	assert.True(t, IsValidEventType("bot.created"))
	assert.True(t, IsValidEventType("bot.updated"))
	assert.True(t, IsValidEventType("bot.deleted"))
	assert.True(t, IsValidEventType("bot.ran"))
	assert.False(t, IsValidEventType("bot.invalid"))
	assert.False(t, IsValidEventType(""))
}
