"""Premissas globais, versionadas em ``config.yaml``.

Manter as premissas fora do codigo permite auditar e variar cenarios sem tocar
na matematica. O ``premissas_hash`` gravado no CSV identifica a combinacao usada.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from ..domain.modelos_ml import MODELOS_ML


class PrevisaoReceita(BaseModel):
    """Parametros do modelo de previsao de receita."""

    modelo: str = Field(default="auto")
    amortecimento: float = Field(default=0.85, gt=0.0, lt=1.0)
    encolhimento_k: float = Field(default=3.0, ge=0.0, le=50.0)
    clip_min: float = Field(default=-0.20, gt=-1.0, lt=0.0)
    clip_max: float = Field(default=0.35, gt=0.0, lt=1.0)
    minimo_anos: int = Field(default=3, ge=2, le=20)
    anos_minimo_backtest: int = Field(default=2014, ge=2010, le=2030)
    minimo_treino: int = Field(default=60, ge=20)
    minimo_obs_setor: int = Field(default=20, ge=5)
    margem_minima: float = Field(default=0.01, ge=0.0, lt=1.0)
    ibc_br_esperado: float = Field(default=0.02, gt=-0.2, lt=0.2)
    ipca_esperado: float = Field(default=0.04, gt=-0.1, lt=0.5)
    cambio_esperado: float = Field(default=0.0, gt=-0.5, lt=0.5)
    # Expectativas do Boletim Focus para o ano a frente (variaveis independentes
    # ex-ante do Modelo B). Desligue com usar_focus: false se o BCB estiver fora.
    usar_focus: bool = Field(default=True)
    ipca_exp_esperado: float = Field(default=0.04, gt=-0.1, lt=0.5)
    pib_exp_esperado: float = Field(default=0.02, gt=-0.2, lt=0.2)
    selic_exp_esperado: float = Field(default=0.11, gt=0.0, lt=0.3)
    cambio_exp_esperado: float = Field(default=0.0, gt=-0.5, lt=0.5)
    # Modelos de machine learning que concorrem no backtest. Cada um usa as
    # features extras de `features.COLUNAS_EXTRA`; biblioteca ausente e apenas
    # ignorada (aviso no log), sem interromper o pipeline.
    modelos_ml: list[str] = Field(default_factory=lambda: list(MODELOS_ML))
    ml_semente: int = Field(default=7, ge=0)
    ml_n_estimadores: int = Field(default=300, ge=50, le=2000)
    ml_profundidade: int = Field(default=3, ge=1, le=8)
    ml_taxa: float = Field(default=0.05, gt=0.0, lt=1.0)
    ml_janela: int = Field(default=3, ge=1, le=10)
    ml_epocas: int = Field(default=80, ge=10, le=2000)

    @field_validator("modelo")
    @classmethod
    def _validar_modelo(cls, valor: str) -> str:
        permitidos = ("auto", "fundamentos", "macro", "AR", "setor", *MODELOS_ML)
        if valor not in permitidos:
            raise ValueError(f"modelo invalido: {valor}; use um de {permitidos}")
        return valor

    @field_validator("modelos_ml")
    @classmethod
    def _validar_modelos_ml(cls, valores: list[str]) -> list[str]:
        desconhecidos = sorted(set(valores) - set(MODELOS_ML))
        if desconhecidos:
            raise ValueError(
                f"modelos_ml invalidos: {desconhecidos}; use subconjunto de {MODELOS_ML}"
            )
        # Preserva a ordem escolhida e remove duplicatas.
        return list(dict.fromkeys(valores))

    def macro_futuro(self) -> dict[str, float]:
        """Premissas macro para o ano a frente, no formato do Modelo B."""
        payload = {
            "d_ibc_br": self.ibc_br_esperado,
            "ipca": self.ipca_esperado,
            "d_cambio": self.cambio_esperado,
        }
        if self.usar_focus:
            payload.update(
                {
                    "ipca_exp": self.ipca_exp_esperado,
                    "pib_exp": self.pib_exp_esperado,
                    "selic_exp": self.selic_exp_esperado,
                    "d_cambio_exp": self.cambio_exp_esperado,
                }
            )
        return payload


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
    publicar_modelo_receita: bool = True
    previsao_receita: PrevisaoReceita = Field(default_factory=PrevisaoReceita)

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


__all__ = ["Config", "PrevisaoReceita", "carregar_config"]
