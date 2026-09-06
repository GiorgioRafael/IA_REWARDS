"""Extrai templates de capturas reais, sem incluir saldo, conta ou anotacoes.

Uso: python tools/train_rewards_app.py --samples logs/rewards_app_training
As tres capturas live_pending/live_search/live_completed devem ter 1103x793.
Para outro layout, ajuste os retangulos apos inspecionar as capturas.
"""
import argparse
import json
from pathlib import Path
from PIL import Image

BASE = Path(__file__).resolve().parents[1]


def train(samples, references=None):
    destination = BASE / "assets" / "rewards_app"
    destination.mkdir(parents=True, exist_ok=True)
    crops = {
        "ganhar_live": ("live_pending", (353, 49, 403, 65)),
        "continuar_live": ("live_pending", (46, 133, 245, 157)),
        "plus10_live": ("live_pending", (175, 536, 208, 559)),
        "voltar_live": ("live_search", (16, 39, 41, 61)),
        "pesquisa_live": ("live_search", (114, 159, 157, 177)),
    }
    for name, (source, rect) in crops.items():
        with Image.open(samples / f"{source}.png") as im:
            if im.size != (1103, 793):
                raise ValueError(f"Dimensoes de {source}: {im.size}; recalibre os recortes.")
            im.crop(rect).save(destination / f"{name}.png")
    if references:
        for path, expected, regions in references:
            with Image.open(path) as im:
                if im.size != expected:
                    raise ValueError(f"Dimensoes inesperadas da referencia: {im.size}")
                for name, rect in regions.items():
                    im.crop(rect).save(destination / f"{name}_reference.png")
    fixtures = BASE / "tests" / "fixtures" / "rewards_app"
    fixtures.mkdir(parents=True, exist_ok=True)
    for state in ("pending", "completed"):
        with Image.open(samples / f"live_{state}.png") as im:
            # Conteudo dos cards, sem cabecalho da conta.
            im.crop((40, 110, 1050, 735)).save(fixtures / f"{state}.png")
    (destination / "training.json").write_text(json.dumps({"method": "RGB template matching with scale search and green badge rejection", "captures": "Microsoft Rewards desktop 1.3.0.0, 1103x793", "crops": crops}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--earn-reference", type=Path)
    parser.add_argument("--badge-reference", type=Path)
    parser.add_argument("--search-reference", type=Path)
    args = parser.parse_args()
    refs = []
    if args.earn_reference:
        refs.append((args.earn_reference, (1603, 913), {"ganhar": (442, 52, 505, 75)}))
    if args.badge_reference:
        refs.append((args.badge_reference, (1738, 774), {"plus10": (720, 424, 763, 451), "continuar": (40, 17, 287, 46)}))
    if args.search_reference:
        refs.append((args.search_reference, (1918, 1079), {"voltar": (20, 39, 48, 67), "pesquisa": (207, 192, 256, 212)}))
    train(args.samples, refs)
