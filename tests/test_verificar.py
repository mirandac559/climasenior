# -*- coding: utf-8 -*-
"""O verificador de coerência roda sobre um painel simulado e acusa um IVC adulterado."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from climasenior import brasil as B        # noqa: E402
from climasenior import verificar as VR    # noqa: E402
from climasenior.simulacao_br import ClienteSimuladoBrasil   # noqa: E402


def test_verificador(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "ANOS_CLIMATOLOGIA", [2022, 2023, 2024, 2025])
    base, site = tmp_path / "data", tmp_path / "site"
    B.executar(ClienteSimuladoBrasil(date(2026, 10, 12)), date(2026, 10, 12), "simulacao", base=base, site=site,
               pausa=0, verbose=False)
    R = VR.verificar(site, base, amostra=4)
    ok = {t for c, t in R.itens if c}
    assert any(t.startswith("71 municípios") for t in ok) and any("dias contínuos" in t for t in ok)
    assert any(t.startswith("4 dias observados") for t in ok)                # IVC publicado = recalculado
    # adultera o IVC de um dia observado: a verificação de igualdade passa a falhar
    meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    for d, f in meta["dias"]:
        if f == "o":
            arq = site / "dia" / f"{d}.json"
            x = json.loads(arq.read_text(encoding="utf-8"))
            x["ivc"] = [None if v is None else min(100, v + 7) for v in x["ivc"]]
            arq.write_text(json.dumps(x), encoding="utf-8")
    R2 = VR.verificar(site, base, amostra=4)
    assert any("dias observados" in t for t in R2.falhas)
