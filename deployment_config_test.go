package main

import (
	"os"
	"strings"
	"testing"
)

func TestHerokuYMLDefinesContainerWebAndWorkerCommands(t *testing.T) {
	content, err := os.ReadFile("heroku.yml")
	if err != nil {
		t.Fatalf("read heroku.yml: %v", err)
	}

	text := string(content)

	requiredSnippets := []string{
		"build:",
		"docker:",
		"web: Dockerfile",
		"run:",
		"- api",
		"- worker",
	}

	for _, snippet := range requiredSnippets {
		if !strings.Contains(text, snippet) {
			t.Fatalf("heroku.yml missing required snippet %q", snippet)
		}
	}
}

func TestDockerfileDefaultCommandMatchesHerokuWebCommand(t *testing.T) {
	content, err := os.ReadFile("Dockerfile")
	if err != nil {
		t.Fatalf("read Dockerfile: %v", err)
	}

	if !strings.Contains(string(content), `CMD ["api"]`) {
		t.Fatalf("Dockerfile must run api by default to match heroku.yml web command")
	}
}
