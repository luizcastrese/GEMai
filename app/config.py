"""Configuração central, lida de variáveis de ambiente (ou arquivo .env)."""
from functools import lru_cache

from pydantic import field_validator, model_validator
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
    # Calibração do ritmo individual pela equipe (services/ritmo.py): mínimo de apontamentos aprovados (ordens
    # distintas) da pessoa por operação e mínimo de operações distintas. Com 1 operação o resultado depende de
    # uma só tarefa; 2 ou mais é mais robusto.
    min_amostras_ritmo: int = 5
    min_operacoes_ritmo: int = 1
    # Calibração por módulo (fator multiplicativo): amostras aprovadas mínimas de um módulo numa unidade.
    min_amostras_calibracao: int = 10
    # Se verdadeiro, o modelo de tempo proposto pela IA e ainda não validado já serve de tempo planejado
    # (rotulado como tal). Se falso, só modelos validados por um gestor entram nas estimativas.
    usar_modelo_ia_nao_validado: bool = True

    # IA
    ia_provedor: str = "auto"  # auto | heuristica | claude
    anthropic_api_key: str = ""
    ia_modelo: str = "claude-opus-5-5"
    ia_timeout_segundos: float = 60.0
    # Busca de ficha técnica na web (ferramenta de servidor da API Anthropic). O tipo segue a documentação vigente;
    # modelos mais antigos exigem a variante básica (web_search_20250305).
    ia_busca_ferramenta: str = "web_search_20260209"
    ia_busca_max_usos: int = 5
    foto_max_bytes: int = 4_000_000  # foto opcional de um meio (JPEG/PNG), descartada após a identificação

    @field_validator("database_url")
    @classmethod
    def _driver_postgres(cls, v: str) -> str:
        # Provedores (Render, Heroku…) entregam "postgres://" ou "postgresql://"; o driver instalado é o psycopg 3.
        for prefixo in ("postgres://", "postgresql://"):
            if v.startswith(prefixo):
                return "postgresql+psycopg://" + v[len(prefixo):]
        return v

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
