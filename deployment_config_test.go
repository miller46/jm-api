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
		"image: web",
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

	text := string(content)

	if !strings.Contains(text, `CMD ["api"]`) {
		t.Fatalf("Dockerfile must run api by default to match heroku.yml web command")
	}

	if !strings.Contains(text, `ENTRYPOINT ["entrypoint.sh"]`) {
		t.Fatalf("Dockerfile must use entrypoint.sh to run migrations on startup")
	}
}

func TestEntrypointRunsMigrations(t *testing.T) {
	content, err := os.ReadFile("entrypoint.sh")
	if err != nil {
		t.Fatalf("read entrypoint.sh: %v", err)
	}

	text := string(content)

	if !strings.Contains(text, "migrate -path /migrations -database") {
		t.Fatalf("entrypoint.sh must run migrations")
	}

	if !strings.Contains(text, `exec "$@"`) {
		t.Fatalf("entrypoint.sh must exec the CMD argument")
	}
}
