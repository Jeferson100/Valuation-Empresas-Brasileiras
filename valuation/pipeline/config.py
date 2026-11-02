"""Premissas globais, versionadas em ``config.yaml``.

Manter as premissas fora do codigo permite auditar e variar cenarios sem tocar
na matematica. O ``premissas_hash`` gravado no CSV identifica a combinacao usada.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Premissas de mercado e de modelagem."""

    rf: float = Field(default=0.105, gt=0.0, lt=0.5)
    erp: float = Field(default=0.075, gt=0.0, lt=0.3)
    kd_fallback: float = Field(default=0.125, gt=0.0, lt=1.0)
    anos_projecao: int = Field(default=5, ge=1, le=15)
    g_perpetuidade: float = Field(default=0.030, ge=0.0, lt=0.1)
    margem_seguranca: float = Field(default=0.25, ge=0.0, lt=1.0)
    upside_max: float = Field(default=0.90, gt=0.0, lt=10.0)
    meio_ano: bool = False
    dias_ultimo_pregao: int = Field(default=5, ge=0, le=60)
    ttl_cache_dias: int = Field(default=1, ge=0, le=365)
    top_readme: int = Field(default=20, ge=1, le=200)
    beta_u_setorial: dict[str, float] = Field(default_factory=dict)
    beta_u_padrao: float = Field(default=0.85, gt=0.0, le=3.0)

    def beta_do_setor(self, setor: str) -> float:
        """Beta desalavancado do setor, com comparacao sem acentos."""
        from ..data.universo import normalizar_texto

        alvo = normalizar_texto(setor).lower()
        for chave, valor in self.beta_u_setorial.items():
            if normalizar_texto(chave).lower() == alvo:
                return float(valor)
        return float(self.beta_u_padrao)

    def hash_premissas(self) -> str:
        """Hash curto das premissas, para auditoria no CSV."""
        payload = self.model_dump(mode="json")
        bruto = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:12]


def carregar_config(caminho: Path | str | None = None) -> Config:
    """Le o YAML; devolve os defaults quando o arquivo nao existe."""
    if caminho is None:
        return Config()

    caminho = Path(caminho)
    if not caminho.exists():
        return Config()

    conteudo = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    return Config.model_validate(conteudo)


__all__ = ["Config", "carregar_config"]
