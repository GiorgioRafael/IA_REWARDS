import threading
import unittest
from unittest.mock import Mock, call, patch

import app_automacao


class FluxoCompletoTests(unittest.TestCase):
    def criar_app_sem_interface(self):
        app = app_automacao.AutoRewardsApp.__new__(app_automacao.AutoRewardsApp)
        app.config = {
            "pesquisas": {
                "executar_conjunto_diario": True,
                "executar_pesquisas": True,
                "delay_apos_conjunto_diario": {"min": 0, "max": 0},
            },
            "brotato": {"executar": True},
            "edge_tempo": {"executar": False},
        }
        app.stop_automation = threading.Event()
        app.marcar_etapa = Mock()
        app.registrar_pontos_etapa = Mock(return_value={"pontos": 100})
        app.garantir_sessao_edge = Mock(return_value=True)
        app.abrir_painel_rewards_sessao = Mock(return_value={"x": 1, "y": 1})
        app.capturar_screenshot_falha = Mock()
        app.status_com_log = Mock()
        app.pressionar_esc_interno = Mock()
        app.sleep_intervalo = Mock(return_value=True)
        app.automation_search_logic = Mock(return_value=True)
        app.dashboard_ativo = Mock(return_value=False)
        app.executar_brotato_logic = Mock(return_value=True)
        app.log_execucao = Mock()
        app.escrever_relatorio_final = Mock()
        app.set_running = Mock()
        return app

    def test_falha_no_conjunto_nao_impede_pesquisas_nem_jogo(self):
        app = self.criar_app_sem_interface()

        with (
            patch.object(app_automacao, "carregar_coordenadas", return_value={}),
            patch.object(app_automacao, "executar_fluxo_inicial", return_value=False),
        ):
            resultado = app.fluxo_completo()

        self.assertFalse(resultado)
        self.assertFalse(app.stop_automation.is_set())
        app.pressionar_esc_interno.assert_called_once_with()
        app.automation_search_logic.assert_called_once()
        app.executar_brotato_logic.assert_called_once_with(com_timer=True)


class PesquisasTests(unittest.TestCase):
    def test_executa_todas_as_23_pesquisas_configuradas(self):
        app = app_automacao.AutoRewardsApp.__new__(app_automacao.AutoRewardsApp)
        app.config = {
            "pesquisas": {
                "search_count": 23,
                "delay_entre_buscas": {"min": 0, "max": 0},
            }
        }
        app.esperar_se_pausado = Mock(return_value=True)
        app.status_com_log = Mock()
        app.log_execucao = Mock()
        app.get_random_words = Mock(
            side_effect=[[f"consulta-{indice}"] for indice in range(1, 24)]
        )
        app.focar_barra_busca = Mock()
        app.write_text_letter_by_letter = Mock()
        app.sleep_interruptivel = Mock(return_value=True)

        with (
            patch.object(app_automacao.pa, "hotkey"),
            patch.object(app_automacao.pa, "press") as press,
            patch.object(app_automacao.random, "uniform", return_value=0),
        ):
            resultado = app.automation_search_logic()

        self.assertTrue(resultado)
        self.assertEqual(23, press.call_args_list.count(call("enter")))
        self.assertEqual(23, app.focar_barra_busca.call_count)
        self.assertEqual(23, app.write_text_letter_by_letter.call_count)


class JogarPCTests(unittest.TestCase):
    def criar_app_sem_interface(self):
        app = app_automacao.AutoRewardsApp.__new__(app_automacao.AutoRewardsApp)
        app.config = {"brotato": {"ignorar_verificacoes": True}}
        app.marcar_etapa = Mock()
        app.abrir_brotato = Mock(return_value=True)
        app.status_com_log = Mock()
        app.focar_jogo_por_janela = Mock(return_value=True)
        app.voltar_para_edge_apos_abrir_jogo = Mock(return_value=True)
        app.capturar_screenshot_falha = Mock()
        return app

    def test_modo_sem_templates_ainda_confirma_janela_do_jogo(self):
        app = self.criar_app_sem_interface()
        app.focar_jogo_por_janela.return_value = False

        resultado = app.executar_brotato_logic(com_timer=False)

        self.assertFalse(resultado)
        app.focar_jogo_por_janela.assert_called_once_with()
        app.voltar_para_edge_apos_abrir_jogo.assert_not_called()
        self.assertIn(
            call(
                "Jogar PC (Brotato)",
                "falhou",
                "O comando foi enviado, mas nenhuma janela do jogo foi encontrada.",
            ),
            app.marcar_etapa.call_args_list,
        )

    def test_jogo_em_background_so_fica_ok_depois_da_espera(self):
        app = self.criar_app_sem_interface()

        resultado = app.executar_brotato_logic(com_timer=False)

        self.assertTrue(resultado)
        self.assertNotIn(
            call("Jogar PC (Brotato)", "ok", "Aberto em background para rodar junto com Edge."),
            app.marcar_etapa.call_args_list,
        )
        self.assertIn(
            call(
                "Jogar PC (Brotato)",
                "em execucao",
                "Janela confirmada; aberto em background junto com Edge.",
            ),
            app.marcar_etapa.call_args_list,
        )


if __name__ == "__main__":
    unittest.main()
