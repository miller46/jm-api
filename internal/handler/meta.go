package handler

import (
	"net/http"

	"github.com/jack/jm-api-go/internal/config"
	"github.com/jack/jm-api-go/internal/model"
)

type MetaHandler struct {
	cfg *config.Config
}

func NewMetaHandler(cfg *config.Config) *MetaHandler {
	return &MetaHandler{cfg: cfg}
}

func (h *MetaHandler) Meta(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, model.MetaResponse{
		Version:     h.cfg.AppVersion,
		GitSHA:      h.cfg.GitSHA,
		DeployedAt:  h.cfg.DeployedAt,
		Environment: h.cfg.Environment,
	})
}
