import unittest
from unittest.mock import patch

import automacao_edge


class FocoScrollTests(unittest.TestCase):
    def test_focar_area_scroll_apenas_posiciona_mouse(self):
        config = {"tempos": {"movimento_mouse": 0}}
        painel = {"origem": "exibir_painel"}

        with (
            patch.object(
                automacao_edge,
                "obter_alvo_area_scroll",
                return_value=(-152, 315, painel),
            ) as obter_alvo,
            patch.object(automacao_edge, "mover_mouse") as mover_mouse,
            patch.object(automacao_edge, "dormir", return_value=True),
            patch.object(
                automacao_edge,
                "garantir_mouse_no_alvo",
                return_value=True,
            ),
            patch.object(automacao_edge, "clicar_mouse") as clicar_mouse,
        ):
            resultado = automacao_edge.focar_area_scroll(config, {})

        self.assertTrue(resultado)
        mover_mouse.assert_called_once_with(-152, 315)
        clicar_mouse.assert_not_called()
        self.assertFalse(obter_alvo.call_args.kwargs["para_clique"])


class EstadoRewardsTests(unittest.TestCase):
    def test_pagina_rewards_completa_e_identificada_pelo_titulo(self):
        config = {"navegador": {}}

        with (
            patch.object(automacao_edge, "obter_janela_ativa", return_value=123),
            patch.object(automacao_edge, "janela_windows_valida", return_value=True),
            patch.object(automacao_edge, "janela_parece_edge", return_value=True),
            patch.object(
                automacao_edge,
                "obter_titulo_janela",
                return_value="Painel de Controle - Microsoft Rewards",
            ),
        ):
            self.assertTrue(automacao_edge.pagina_rewards_completa_ativa(config))

    def test_estado_nao_confunde_pagina_completa_com_painel_lateral(self):
        config = {"navegador": {}}

        with (
            patch.object(automacao_edge, "obter_janela_ativa", return_value=123),
            patch.object(automacao_edge, "janela_windows_valida", return_value=True),
            patch.object(automacao_edge, "janela_parece_edge", return_value=True),
            patch.object(
                automacao_edge,
                "obter_titulo_janela",
                return_value="Painel de Controle - Microsoft Rewards",
            ),
            patch.object(
                automacao_edge,
                "listar_templates_alvo_visual",
                return_value=["template"],
            ),
            patch.object(
                automacao_edge,
                "detectar_alvo_visual_visivel_e_cachear",
                return_value=(-152, 315, {"score": 1.0}),
            ),
            patch.object(
                automacao_edge,
                "obter_regiao_painel_rewards",
                return_value=None,
            ),
        ):
            estado = automacao_edge.detectar_estado_rewards_atual(config)

        self.assertEqual("pagina_rewards_completa", estado["estado"])
        self.assertFalse(estado["ok"])

    def test_pagina_completa_invalida_cache_do_painel_lateral(self):
        config = {
            "_runtime_cache": {
                "alvos_visuais": {"exibir_painel": {"x": 10, "y": 20}},
                "painel_rewards": {"x": 1, "y": 2, "width": 400, "height": 900},
            }
        }

        with (
            patch.object(
                automacao_edge,
                "pagina_rewards_completa_ativa",
                return_value=True,
            ),
            patch.object(automacao_edge, "detectar_painel_atual") as detectar_painel,
        ):
            painel = automacao_edge.obter_regiao_painel_rewards(config)

        self.assertIsNone(painel)
        self.assertNotIn("exibir_painel", config["_runtime_cache"]["alvos_visuais"])
        self.assertIsNone(config["_runtime_cache"]["painel_rewards"])
        detectar_painel.assert_not_called()

    def test_recupera_painel_apos_navegacao_indevida(self):
        config = {}
        coordenadas = {"icone_extensao": (1, 2)}

        with (
            patch.object(
                automacao_edge,
                "pagina_rewards_completa_ativa",
                side_effect=[True, False],
            ),
            patch.object(automacao_edge, "limpar_cache_execucao") as limpar_cache,
            patch.object(automacao_edge.pyautogui, "hotkey") as hotkey,
            patch.object(automacao_edge, "dormir", return_value=True),
            patch.object(
                automacao_edge,
                "garantir_painel_rewards_visivel",
                return_value=True,
            ) as garantir_painel,
        ):
            resultado = automacao_edge.recuperar_painel_rewards_apos_navegacao(
                config,
                coordenadas,
            )

        self.assertTrue(resultado)
        limpar_cache.assert_called_once_with(config)
        hotkey.assert_called_once_with("alt", "left")
        garantir_painel.assert_called_once()


class FallbackRewardsTests(unittest.TestCase):
    def test_fallback_web_nao_envia_esc_global(self):
        config = {
            "navegador": {},
            "rewards_estado": {
                "usar_fallback_web_painel": True,
                "fallback_web_delay_bing_segundos": 0,
                "fallback_web_delay_painel_segundos": 0,
            },
        }

        with (
            patch.object(automacao_edge, "obter_janela_ativa", return_value=123),
            patch.object(automacao_edge, "janela_windows_valida", return_value=True),
            patch.object(automacao_edge, "janela_parece_edge", return_value=True),
            patch.object(automacao_edge, "dormir", return_value=True),
            patch.object(automacao_edge.pyautogui, "press") as press,
            patch.object(automacao_edge.pyautogui, "hotkey") as hotkey,
            patch.object(automacao_edge.pyautogui, "write"),
            patch("pyperclip.paste", return_value="clipboard anterior"),
            patch("pyperclip.copy"),
        ):
            resultado = automacao_edge.abrir_painel_rewards_fallback_web(config)

        self.assertTrue(resultado)
        self.assertNotIn("esc", [chamada.args[0] for chamada in press.call_args_list])
        self.assertEqual(2, [chamada.args for chamada in press.call_args_list].count(("enter",)))
        self.assertEqual(2, [chamada.args for chamada in hotkey.call_args_list].count(("ctrl", "l")))


if __name__ == "__main__":
    unittest.main()
