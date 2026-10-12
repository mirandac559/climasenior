# -*- coding: utf-8 -*-
"""Modelos do ClimaSênior: classificação de risco, previsão de demanda e composição do IVC."""
from __future__ import annotations
import json, joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                             mean_absolute_error, mean_squared_error, brier_score_loss)
from .config import (TREINO_ATE, VALIDACAO_DE, VALIDACAO_ATE, TESTE_DE, DIR_MODELOS,
                     PESO_EXPOSICAO, PESO_SENSIBILIDADE, PESO_CAPACIDADE)
from .atributos import ATRIBUTOS


def divisao_temporal(df: pd.DataFrame):
    """Divisão estritamente temporal (sem vazamento de informação futura)."""
    tr = df[df["data"] <= TREINO_ATE]
    va = df[(df["data"] >= VALIDACAO_DE) & (df["data"] <= VALIDACAO_ATE)]
    te = df[df["data"] >= TESTE_DE]
    return tr, va, te


class ModeloLSTM:
    """
    Componente de previsão de demanda por rede recorrente. Requer TensorFlow.
    Quando indisponível, o pipeline usa GradientBoosting como linha de base com
    interface idêntica (fit/predict), o que mantém a esteira executável.
    """
    def __init__(self, janela: int = 14):
        self.janela = janela
        self.disponivel = False
        try:
            import tensorflow as tf  # noqa
            self.disponivel = True
        except Exception:
            self.disponivel = False
        self._base = GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                               learning_rate=0.05, random_state=42)

    def fit(self, X, y):
        if not self.disponivel:
            self._base.fit(X, y); return self
        import tensorflow as tf
        Xs = np.asarray(X, dtype="float32")[:, None, :]
        m = tf.keras.Sequential([
            tf.keras.layers.LSTM(32, input_shape=(1, Xs.shape[-1])),
            tf.keras.layers.Dense(1)])
        m.compile(optimizer="adam", loss="mae")
        m.fit(Xs, np.asarray(y, dtype="float32"), epochs=30, batch_size=64, verbose=0)
        self._keras = m
        return self

    def predict(self, X):
        if not self.disponivel:
            return self._base.predict(X)
        return self._keras.predict(np.asarray(X, dtype="float32")[:, None, :], verbose=0).ravel()


class ClimaSeniorModelos:
    """Agrupa os três componentes e a composição do IVC."""

    def __init__(self):
        self.rf = RandomForestClassifier(n_estimators=300, max_depth=10,
                                         class_weight="balanced", random_state=42)
        self.demanda = ModeloLSTM()
        self.scaler = StandardScaler()
        self.logit = LogisticRegression(max_iter=2000, class_weight="balanced")
        self.metricas: dict = {}

    # ------------------------------------------------------------- treino
    def treinar(self, df: pd.DataFrame):
        tr, va, te = divisao_temporal(df)
        Xtr, Xva, Xte = tr[ATRIBUTOS], va[ATRIBUTOS], te[ATRIBUTOS]

        self.rf.fit(Xtr, tr["risco"])
        self.demanda.fit(Xtr, tr["atend_alvo"])
        self.scaler.fit(Xtr)
        self.logit.fit(self.scaler.transform(Xtr), (tr["risco"] == 2).astype(int))

        for nome, X, sub in [("validacao", Xva, va), ("teste_2025", Xte, te)]:
            p = self.rf.predict(X)
            d = self.demanda.predict(X)
            prob = self.logit.predict_proba(self.scaler.transform(X))[:, 1]
            self.metricas[nome] = {
                "risco_acuracia": round(accuracy_score(sub["risco"], p), 3),
                "risco_precisao_macro": round(precision_score(sub["risco"], p, average="macro", zero_division=0), 3),
                "risco_recall_macro": round(recall_score(sub["risco"], p, average="macro", zero_division=0), 3),
                "risco_f1_macro": round(f1_score(sub["risco"], p, average="macro", zero_division=0), 3),
                "demanda_MAE": round(mean_absolute_error(sub["atend_alvo"], d), 2),
                "demanda_RMSE": round(float(np.sqrt(mean_squared_error(sub["atend_alvo"], d))), 2),
                "ivc_brier": round(brier_score_loss((sub["risco"] == 2).astype(int), prob), 3),
                "n": int(len(sub)),
            }
        imp = sorted(zip(ATRIBUTOS, self.rf.feature_importances_), key=lambda x: -x[1])
        self.metricas["importancia_variaveis"] = [{"variavel": v, "importancia": round(float(i), 3)} for v, i in imp]
        self.metricas["lstm_disponivel"] = self.demanda.disponivel
        return self

    # ------------------------------------------------------------- IVC
    def calcular_ivc(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[ATRIBUTOS]
        prob_alto = self.logit.predict_proba(self.scaler.transform(X))[:, 1]
        # exposição = probabilidade de risco alto (dinâmica); sensibilidade e capacidade
        # são componentes territoriais (estruturais). Pesos pactuáveis com gestores.
        sens = np.clip(df["prev_comorb"].values * df["prop_idosos"].values / 0.07, 0, 1)
        cap = 1 - df["cap_resposta"].values
        ivc = 100 * (PESO_EXPOSICAO * prob_alto + PESO_SENSIBILIDADE * sens + PESO_CAPACIDADE * cap)
        out = df[["data", "cod_ibge", "municipio", "tmax", "ind_calor", "dias_consec_calor",
                  "atend_idosos", "risco"]].copy()
        out["demanda_prevista_d3"] = np.round(self.demanda.predict(X), 1)
        out["risco_previsto"] = self.rf.predict(X)
        out["prob_risco_alto"] = np.round(prob_alto, 3)
        out["IVC"] = np.round(np.clip(ivc, 0, 100), 1)
        return out

    # ------------------------------------------------------------- persistência
    def salvar(self, versao: str = "v1"):
        joblib.dump(self, DIR_MODELOS / f"climasenior_{versao}.joblib")
        with open(DIR_MODELOS / f"metricas_{versao}.json", "w", encoding="utf-8") as f:
            json.dump(self.metricas, f, ensure_ascii=False, indent=2)

    @staticmethod
    def carregar(versao: str = "v1") -> "ClimaSeniorModelos":
        return joblib.load(DIR_MODELOS / f"climasenior_{versao}.joblib")
