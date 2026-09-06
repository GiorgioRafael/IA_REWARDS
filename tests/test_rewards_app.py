import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from rewards_app import DetectorRewardsApp, FluxoRewardsApp, RewardsAppError
from app_config import DEFAULT_CONFIG, mesclar_config
import test_app_automacao

FIXTURES = Path(__file__).parent / "fixtures" / "rewards_app"


class DetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = DetectorRewardsApp()

    def test_pendente_e_concluidos_em_varias_escalas(self):
        for state, count in (("pending", 1), ("completed", 0), ("held_out", 1)):
            with Image.open(FIXTURES / f"{state}.png") as image:
                for scale in (0.8, 1.0, 1.25, 1.5):
                    with self.subTest(state=state, scale=scale):
                        scaled = image.resize((round(image.width * scale), round(image.height * scale)))
                        self.assertEqual(count, len(self.detector.find(scaled, "plus10")))

    def test_fundo_vazio_nao_tem_alvo(self):
        image = Image.new("RGB", (1103, 793), (23, 27, 42))
        for name in self.detector.templates:
            self.assertEqual([], self.detector.find(image, name))


class FakeDriver:
    def __init__(self, remaining=1, stuck=False, section=True, search=True):
        self.remaining = remaining
        self.stuck = stuck
        self.section = section
        self.search = search
        self.page = 0
        self.searching = False
        self.opened = self.back = self.scrolls = 0

    def open(self):
        self.opened += 1

    def capture(self):
        shade = 20 + self.page * 30 + self.remaining * 40
        im = Image.new("RGB", (600, 600), (shade, shade, shade))
        if self.searching:
            targets = ["voltar", "pesquisa"] if self.search else []
        else:
            targets = ["ganhar"]
            if self.page == 1 and self.section:
                targets += ["continuar"]
                if self.remaining:
                    targets += ["plus10"]
        im.info["targets"] = targets
        return im

    def click(self, target):
        if target["name"] == "plus10":
            self.searching = True
        elif target["name"] == "voltar":
            self.back += 1
            self.searching = False
            if not self.stuck:
                self.remaining -= 1

    def home(self):
        self.page = 0

    def scroll(self):
        self.page = min(2, self.page + 1)
        self.scrolls += 1

    def wait(self, seconds):
        pass


class FakeDetector:
    def find(self, image, name):
        if name not in image.info["targets"]:
            return []
        return [dict(name=name, x=150, y=300 if name == "plus10" else 120, width=30, height=20, score=1)]


class FlowTests(unittest.TestCase):
    def flow(self, driver, **settings):
        return FluxoRewardsApp(driver, FakeDetector(), dict(max_scrolls=6, **settings))

    def test_abre_pesquisa_volta_e_varre_ate_nao_ter_mais(self):
        driver = FakeDriver(remaining=3)
        result = self.flow(driver).run()
        self.assertEqual(3, result["cards_abertos"])
        self.assertEqual(3, driver.back)
        self.assertTrue(result["fim_confirmado"])
        self.assertGreaterEqual(driver.scrolls, 6)

    def test_pagina_ja_concluida_nao_clica(self):
        driver = FakeDriver(remaining=0)
        result = self.flow(driver).run()
        self.assertEqual(0, result["cards_abertos"])
        self.assertEqual(0, driver.back)

    def test_card_que_nao_credita_falha_sem_loop_infinito(self):
        driver = FakeDriver(stuck=True)
        with self.assertRaisesRegex(RewardsAppError, "mesmo card"):
            self.flow(driver).run()
        self.assertEqual(2, driver.back)

    def test_secao_ausente_nao_e_sucesso(self):
        driver = FakeDriver(section=False)
        with self.assertRaisesRegex(RewardsAppError, "Secao"):
            self.flow(driver).run()
        self.assertEqual(0, driver.back)

    def test_limite_com_pendencias_nao_e_sucesso(self):
        with self.assertRaisesRegex(RewardsAppError, "Limite de cards"):
            self.flow(FakeDriver(remaining=2), max_cards=1).run()

    def test_pesquisa_nao_carrega_nao_clica_voltar(self):
        driver = FakeDriver(search=False)
        with self.assertRaisesRegex(RewardsAppError, "Timeout aguardando pesquisa"):
            self.flow(driver, timeout_segundos=0.005).run()
        self.assertEqual(0, driver.back)

    def test_cancelamento_interrompe(self):
        driver = FakeDriver()
        with patch.object(driver, "capture", side_effect=RewardsAppError("Execucao interrompida")):
            with self.assertRaisesRegex(RewardsAppError, "interrompida"):
                self.flow(driver).run()


class IntegrationTests(unittest.TestCase):
    def app(self):
        app = test_app_automacao.FluxoCompletoTests().criar_app_sem_interface()
        app.config = mesclar_config(DEFAULT_CONFIG, {})
        app.config["pesquisas"]["executar_conjunto_diario"] = False
        app.config["pesquisas"]["executar_pesquisas"] = False
        return app

    def test_somente_rewards_app_e_fluxo_valido(self):
        app = self.app()
        self.assertTrue(app.fluxo_selecionado_existe())
        with patch("app_automacao.executar_rewards_app", return_value={"cards_abertos": 2}) as execute:
            self.assertTrue(app.fluxo_completo())
        execute.assert_called_once()
        app.automation_search_logic.assert_not_called()

    def test_falha_app_nao_marca_fluxo_sucesso(self):
        app = self.app()
        with patch("app_automacao.executar_rewards_app", side_effect=RewardsAppError("sem janela")):
            self.assertFalse(app.fluxo_completo())

    def test_fluxo_agendado_preserva_nova_opcao(self):
        app = self.app()
        scheduled = app.obter_fluxo_agendamento_config()
        self.assertTrue(scheduled["executar_rewards_app"])
        app.aplicar_fluxo_config(dict(executar_rewards_app=False))
        self.assertFalse(app.config["rewards_app"]["executar"])
        app.aplicar_fluxo_config(scheduled)
        self.assertTrue(app.config["rewards_app"]["executar"])
