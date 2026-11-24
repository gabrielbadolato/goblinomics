import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from ahforever import addon


class Falso:
    """O mínimo de consulta.Dados que o addon usa."""
    coletado_em = "2026-11-24T20:40:35Z"
    casa = {"nome": "Horde Auction House", "id": 114}
    precos = {10: [500, 520, 7], 20: [900, 950, 3]}
    habituais = {10: 400.4, 30: 80}
    por_dia = {10: 12.34}

    def preco(self, i):
        minimo, _, qtd = self.precos.get(i, (None, None, 0))
        return {"min": minimo, "habitual": self.habituais.get(i), "por_dia": self.por_dia.get(i), "qtd": qtd}

    def fabricar(self, i):
        if i != 20:
            return []
        return [{"custo": 600, "lucro": 200, "feitos": 2}, {"custo": None, "lucro": None, "feitos": 1},
                {"custo": 100, "lucro": 50, "feitos": 1}]


class TestAddon(unittest.TestCase):
    def test_linhas_trazem_so_o_que_existe_e_a_receita_que_mais_rende(self):
        self.assertEqual(addon.linhas(Falso()), [
            "[10]={m=500,h=400,d=12.3,q=7},",
            "[20]={m=900,q=3,c=300,l=100},",   # custo e lucro por unidade fabricada (2 por vez)
            "[30]={h=80},",
        ])

    def test_lua_tem_a_hora_da_coleta_e_a_contagem(self):
        texto = addon.lua(Falso())
        self.assertIn("GoblinomicsDados = {", texto)
        self.assertIn("coletado=1795552835,", texto)
        self.assertIn('casa="Horde Auction House 114",', texto)
        self.assertIn("n=3,", texto)
        self.assertEqual(texto.count("{"), texto.count("}"))

    def test_gerar_grava_o_arquivo_e_o_zip_com_crlf_nos_scripts(self):
        with tempfile.TemporaryDirectory() as pasta:
            cfg = SimpleNamespace(pasta_site=Path(pasta), casa_padrao=114)
            falso = Falso()
            falso.atualizar = lambda: True
            original, addon.consulta.Dados = addon.consulta.Dados, lambda *a: falso
            try:
                addon.gerar(cfg)
            finally:
                addon.consulta.Dados = original
            self.assertIn(b"[30]={h=80},", (Path(pasta) / "addon" / "Dados.lua").read_bytes())
            with zipfile.ZipFile(Path(pasta) / "addon" / "Goblinomics.zip") as z:
                nomes = z.namelist()
                self.assertIn("Goblinomics/Goblinomics.toc", nomes)
                self.assertIn("Goblinomics/Dados.lua", nomes)
                bat = z.read("Goblinomics/atualizar.bat")
                self.assertIn(b"\r\n", bat)
                self.assertNotIn(b"\r\r", bat)
                self.assertNotIn(b"\r\n", z.read("Goblinomics/Goblinomics.lua"))


if __name__ == "__main__":
    unittest.main()
