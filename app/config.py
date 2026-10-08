"""Configuração central, lida de variáveis de ambiente (ou arquivo .env)."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_PADRAO = "dev-only-insecure-secret-change-me-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ERP_", extra="ignore")

    ambiente: str = "desenvolvimento"  # desenvolvimento | producao
    database_url: str = "sqlite:///./erp.db"
    secret_key: str = _SECRET_PADRAO
    token_minutos: int = 60
    permitir_cadastro_publico: bool = True
    cors_origens: str = ""  # lista separada por vírgula; vazio = mesma origem apenas
    max_tentativas_login: int = 5
    bloqueio_minutos: int = 15
    senha_minima: int = 10

    # Estimativas
    min_amostras_historico: int = 3

    # IA
    ia_provedor: str = "auto"  # auto | heuristica | claude
    anthropic_api_key: str = ""
    ia_modelo: str = "claude-opus-5-5"
    ia_timeout_segundos: float = 60.0

    @property
    def producao(self) -> bool:
        return self.ambiente.lower() in ("producao", "produção", "production", "prod")

    @model_validator(mode="after")
    def _valida_producao(self):
        if self.producao:
            if self.secret_key == _SECRET_PADRAO or len(self.secret_key) < 32:
                raise ValueError("Em produção, ERP_SECRET_KEY deve ser definido com 32+ caracteres.")
        return self

    @property
    def origens_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origens.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
