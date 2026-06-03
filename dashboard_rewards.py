import re
from datetime import datetime, timezone

import requests


def limpar_texto_clipboard(texto):
    if texto is None:
        return ""
    return str(texto).strip().replace("\u200e", "")


def normalizar_pontos_texto(texto):
    texto = limpar_texto_clipboard(texto)
    if not texto:
        return None

    candidatos = re.findall(r"\d[\d.,\s]*", texto)
    if not candidatos:
        return None

    melhor = max(candidatos, key=len)
    apenas_digitos = re.sub(r"\D", "", melhor)
    if not apenas_digitos:
        return None

    try:
        return int(apenas_digitos)
    except ValueError:
        return None


def _int_config_opcional(config, nome):
    valor = config.get(nome)
    if valor is None or valor == "":
        return None

    try:
        inteiro = int(valor)
    except (TypeError, ValueError):
        return None

    if inteiro <= 0:
        return None
    return inteiro


def _texto_tem_formato_saldo(texto):
    texto = limpar_texto_clipboard(texto)
    texto_sem_espacos = re.sub(r"\s+", "", texto)
    if not texto_sem_espacos:
        return False

    if "." in texto_sem_espacos and "," in texto_sem_espacos:
        return False

    separador = "." if "." in texto_sem_espacos else "," if "," in texto_sem_espacos else None
    if not separador:
        return texto_sem_espacos.isdigit()

    partes = texto_sem_espacos.split(separador)
    if any(not parte.isdigit() for parte in partes):
        return False

    primeira, restantes = partes[0], partes[1:]
    if not 1 <= len(primeira) <= 3:
        return False

    return bool(restantes) and all(len(parte) == 3 for parte in restantes)


def validar_leitura_pontos(texto, pontos, config=None, ultimo_pontos=None):
    config = config or {}
    texto_limpo = limpar_texto_clipboard(texto)

    if pontos is None:
        return False, "sem_numero"

    max_texto = int(config.get("max_raw_text_chars", 40))
    if len(texto_limpo) > max_texto:
        return False, f"texto_muito_longo:{len(texto_limpo)}"

    if re.search(r"[A-Za-zÀ-ÿ]", texto_limpo):
        return False, "texto_contem_letras"

    if not re.fullmatch(r"[\d\s.,]+", texto_limpo):
        return False, "texto_tem_caracteres_invalidos"

    if not _texto_tem_formato_saldo(texto_limpo):
        return False, "formato_numero_invalido"

    pontos_minimos = _int_config_opcional(config, "min_points")
    if pontos_minimos is not None and pontos < pontos_minimos:
        return False, f"pontos_abaixo_minimo:{pontos_minimos}"

    max_queda = _int_config_opcional(config, "max_auto_drop")
    if max_queda is not None and ultimo_pontos is not None and pontos < ultimo_pontos - max_queda:
        return False, f"queda_absurda:{ultimo_pontos - pontos}"

    return True, "ok"


def agora_iso_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def valor_firestore(valor):
    if valor is None:
        return {"nullValue": None}
    if isinstance(valor, bool):
        return {"booleanValue": valor}
    if isinstance(valor, int):
        return {"integerValue": str(valor)}
    if isinstance(valor, float):
        return {"doubleValue": valor}
    if isinstance(valor, dict):
        return {
            "mapValue": {
                "fields": {
                    str(chave): valor_firestore(item)
                    for chave, item in valor.items()
                    if item is not None
                }
            }
        }
    if isinstance(valor, (list, tuple)):
        return {
            "arrayValue": {
                "values": [valor_firestore(item) for item in valor]
            }
        }
    return {"stringValue": str(valor)}


def documento_firestore(payload):
    fields = {}
    for chave, valor in payload.items():
        if chave == "createdAt":
            fields[chave] = {"timestampValue": str(valor)}
        elif valor is not None:
            fields[chave] = valor_firestore(valor)
    return {"fields": fields}


class DashboardRewardsClient:
    def __init__(self, config):
        self.config = config or {}

    def ativo(self):
        return bool(self.config.get("ativada", False))

    def enviar_evento(self, payload):
        if not self.ativo():
            return {"ok": False, "skipped": True, "reason": "dashboard_desativado"}

        endpoint = (self.config.get("api_endpoint") or "").strip()
        if endpoint:
            return self._enviar_api(endpoint, payload)

        return self._enviar_firestore(payload)

    def _enviar_api(self, endpoint, payload):
        headers = {"Content-Type": "application/json"}
        secret = (self.config.get("api_secret") or "").strip()
        if secret:
            headers["X-Rewards-Secret"] = secret

        response = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        if response.status_code >= 400:
            return {
                "ok": False,
                "status_code": response.status_code,
                "response": response.text[:500],
            }

        return {"ok": True, "status_code": response.status_code, "mode": "api"}

    def _enviar_firestore(self, payload):
        firebase = self.config.get("firebase") or {}
        api_key = (firebase.get("apiKey") or "").strip()
        project_id = (firebase.get("projectId") or "").strip()
        user_uid = (self.config.get("user_uid") or "").strip()

        if not api_key or not project_id:
            return {"ok": False, "reason": "firebase_config_incompleta"}
        if not user_uid:
            return {"ok": False, "reason": "user_uid_nao_configurado"}

        url = (
            "https://firestore.googleapis.com/v1/projects/"
            f"{project_id}/databases/(default)/documents/users/"
            f"{user_uid}/rewardEvents?key={api_key}"
        )

        headers = {"Content-Type": "application/json"}
        bearer = (self.config.get("bearer_token") or "").strip()
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        response = requests.post(
            url,
            json=documento_firestore(payload),
            headers=headers,
            timeout=15,
        )
        if response.status_code >= 400:
            return {
                "ok": False,
                "status_code": response.status_code,
                "response": response.text[:500],
            }

        return {
            "ok": True,
            "status_code": response.status_code,
            "mode": "firestore_rest",
        }
