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
    npc = {10: 480}
    # item fabricado -> [(receita, profissão, nome, feitos, reagentes)]; o 20 leva dois do 10
    receitas = {20: [(1, 171, "Coisa", 2, [[10, 2]])]}
    ensina = {20: [[40, 150]]}

    def preco(self, i):
        minimo, _, qtd = self.precos.get(i, (None, None, 0))
        return {"min": minimo, "habitual": self.habituais.get(i), "por_dia": self.por_dia.get(i), "qtd": qtd,
                "npc_paga": self.npc.get(i)}

    def fabricar(self, i):
        if i != 20:
            return []
        return [{"custo": 600, "lucro": 200, "feitos": 2, "quem": ["Zé", "Ana"]}, {"custo": None, "lucro": None, "feitos": 1},
                {"custo": 100, "lucro": 50, "feitos": 1, "quem": ["Ana"]}]


class TestAddon(unittest.TestCase):
    def test_linhas_trazem_so_o_que_existe_e_a_receita_que_mais_rende(self):
        self.assertEqual(addon.linhas(Falso()), [
            # n: o NPC paga 480, mais que os 500 do leilão sem a taxa; u/ul: entra em 1 receita, que dá lucro
            "[10]={m=500,h=400,d=12.3,q=7,n=480,u=1,ul=1},",
            # custo e lucro por unidade fabricada (2 por vez); g quem faz; r o item que ensina a receita
            '[20]={m=900,q=3,c=300,l=100,g="Ana, Zé",r=40},',
            "[30]={h=80},",
        ])

    def test_origem_da_receita_e_mapas_viram_frases(self):
        origens = {"zonas": {"1637": ["Orgrimmar", "Orgrimmar"], "10": ["Duskwood", "Floresta do Crepúsculo"]},
                   "npcs": {"1": ["Elynna", None, "A", 30, 30], "2": ["Borya", 1637, "H", 30, 30],
                            "3": ["Skeletal Fiend", 10, "", 24, 25]},
                   "itens": {"40": {"v": [1, 2], "d": [3], "dn": 1, "q": 2}, "41": {"d": [3], "dn": 99}}}
        zonas = {"zonas": {"felwood": {"en": "Felwood"}, "wpl": {"en": "Western Plaguelands"}},
                 "materiais": {"30": {"zonas": ["wpl", "felwood"]}}}
        linhas = dict(l.split("=", 1) for l in addon.linhas(Falso(), origens, zonas))
        # A casa é da Horda: o vendedor dela vem primeiro e sem rótulo; o da Aliança fica marcado.
        self.assertEqual(linhas["[40]"], '{o="vendido por Borya (Orgrimmar), Elynna (Aliança); '
                         'cai de Skeletal Fiend (nv 24-25, Duskwood); recompensa de 2 missões"},')
        self.assertEqual(linhas["[41]"], '{o="queda mundial (99 monstros)"},')
        self.assertEqual(linhas["[30]"], '{h=80,z="Western Plaguelands, Felwood"},')

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
            self.assertIn(b"SLASH_GOBLINOMICS1", (Path(pasta) / "addon" / "Goblinomics.lua").read_bytes())
            self.assertIn(b"Interface", (Path(pasta) / "addon" / "Goblinomics.toc").read_bytes())
            base = Path(pasta) / "addon"
            self.assertEqual((base / "arquivos.txt").read_bytes().split(b"\r\n")[:2],
                             [b"Dados.lua GoblinomicsDados", b"Goblinomics.lua SLASH_GOBLINOMICS1"])
            self.assertIn(b"\r\n", (base / "atualizar.bat").read_bytes())
            self.assertEqual((base / "Icone.tga").read_bytes(), (addon.FONTES / "Icone.tga").read_bytes())
            with zipfile.ZipFile(Path(pasta) / "addon" / "Goblinomics.zip") as z:
                nomes = z.namelist()
                self.assertIn("Goblinomics/Goblinomics.toc", nomes)
                self.assertIn("Goblinomics/Dados.lua", nomes)
                self.assertIn("Goblinomics/Icone.tga", nomes)
                bat = z.read("Goblinomics/atualizar.bat")
                self.assertIn(b"\r\n", bat)
                self.assertNotIn(b"\r\r", bat)
                self.assertNotIn(b"\r\n", z.read("Goblinomics/Goblinomics.lua"))


if __name__ == "__main__":
    unittest.main()
