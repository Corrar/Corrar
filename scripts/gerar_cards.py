#!/usr/bin/env python3
"""Gera os cards SVG do README de perfil, no estilo terminal.

Busca os dados pela API GraphQL do GitHub e desenha:
  whoami.svg         avatar em ASCII, apresentação, números do ano e linguagens
  analytics.svg      total, sequência atual e maior sequência + atividade dos últimos 30 dias
  contribuicoes.svg  mapa de contribuições dos últimos 12 meses
  cobrinha.svg       a cobrinha do Platane/snk dentro da mesma janela (com --cobra)

Uso:
  GITHUB_TOKEN=... python gerar_cards.py --usuario Corrar --saida dist
  python gerar_cards.py --demo --saida dist     # dados fictícios, sem rede (pré-visualização)

Opções úteis: --tema verde|rosa · --imagem avatar.png (usa outra imagem no ASCII).
Só a biblioteca padrão é obrigatória; com Pillow instalado o avatar vira ASCII.
"""

import argparse
import datetime as dt
import io
import json
import os
import random
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

# ---------------------------------------------------------------- edite aqui
PERFIL = {
    "nome": "Bruno Corral",
    "cargo": "Dev full stack",
    "bio": [
        "Sistemas de gestão, sites para negócios locais",
        "e automações com IA.",
        "Fatec Adamantina · interior de SP 🇧🇷",
    ],
}

TEMAS = {
    "verde": {
        "fundo": "#0d1117", "barra": "#161b22", "caixa": "#11161d", "borda": "#30363d",
        "texto": "#e6edf3", "suave": "#8b949e", "destaque": "#39d353", "prompt": "#3fb950",
        "caminho": "#58a6ff",
        "niveis": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
    },
    "rosa": {
        "fundo": "#0f0d13", "barra": "#18141d", "caixa": "#141118", "borda": "#2f2737",
        "texto": "#f4e9f1", "suave": "#a3909e", "destaque": "#ff79c6", "prompt": "#ff79c6",
        "caminho": "#bd93f9",
        "niveis": ["#1d1923", "#4a1d3d", "#7a2a5f", "#c23f8a", "#ff79c6"],
    },
}
# ---------------------------------------------------------------------------

LARGURA = 900
FONTE = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
RAMPA = " .:-=+*#%@"
NBSP = " "
# Logo do Corrar em ASCII, usado se o avatar não puder ser baixado.
ASCII_RESERVA = [
    '             -#%@@@@@@@@@@@@@@@@@@@@@-',
    '           :%@@+:#@@@@@@@@@@@@@@@@@@*',
    '         :*@@@@+  -#@@@@@@@@@@@@@@+',
    '       .+@@@@@@+    -%@@@@@@@@@@+',
    '     .+@@@@@@@@+      =%@@@@@@*.',
    '   .+@@@@@@@@@@+        =@@@#:',
    '  :@@@@@@@@@@@@+          -:',
    '  :@@@@@@@@@@@@+',
    '  :@@@@@@@@@@@@+',
    '  :@@@@@@@@@@@@+',
    '  .#%#####%%%%@%+====================.',
    '              =@@@@@@@@@@@@@@@@@@@@@@-',
    '              -@@@@@@@@@@@@@@@@@@@@+.',
    '              -@@@@@@@@@@@@@@@@@@=',
    '              -@@@@@@@@@@@@@@@@+.',
    '              -@@@@@@@@@@@@@@*.',
    '              :%@@@@@@@@@@@#:',
]

CONSULTA_USUARIO = """
query($login: String!) {
  user(login: $login) {
    login createdAt avatarUrl(size: 240)
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
      totalCount
      nodes { languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
        edges { size node { name color } } } }
    }
  }
}"""

CONSULTA_CALENDARIO = """
query($login: String!, $de: DateTime!, $ate: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $de, to: $ate) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


# ------------------------------------------------------------------- dados

def graphql(token, consulta, variaveis):
    corpo = json.dumps({"query": consulta, "variables": variaveis}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=corpo,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "gerar-cards-perfil"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        dados = json.load(resp)
    if dados.get("errors"):
        raise SystemExit(f"Erro da API do GitHub: {dados['errors']}")
    return dados["data"]


def baixar(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read()
    except OSError:
        return None


def buscar(usuario, token):
    u = graphql(token, CONSULTA_USUARIO, {"login": usuario})["user"]
    if not u:
        raise SystemExit(f"Usuário '{usuario}' não encontrado.")
    criado = dt.datetime.fromisoformat(u["createdAt"].replace("Z", "+00:00"))
    agora = dt.datetime.now(dt.timezone.utc)

    # A API devolve no máximo 1 ano por consulta: percorre desde a criação da conta.
    dias = {}
    inicio = criado
    while inicio < agora:
        fim = min(inicio + dt.timedelta(days=364), agora)
        cal = graphql(token, CONSULTA_CALENDARIO,
                      {"login": usuario, "de": inicio.isoformat(), "ate": fim.isoformat()})
        semanas = cal["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for semana in semanas:
            for d in semana["contributionDays"]:
                data = dt.date.fromisoformat(d["date"])
                dias[data] = max(dias.get(data, 0), d["contributionCount"])
        inicio = fim

    linguagens = defaultdict(lambda: [0, None])
    for repo in u["repositories"]["nodes"]:
        for aresta in repo["languages"]["edges"]:
            item = linguagens[aresta["node"]["name"]]
            item[0] += aresta["size"]
            item[1] = aresta["node"]["color"] or item[1]

    return {
        "login": u["login"], "criado": criado.date(), "hoje": agora.date(), "dias": dias,
        "repos": u["repositories"]["totalCount"],
        "linguagens": {nome: (tam, cor or "#8b949e") for nome, (tam, cor) in linguagens.items()},
        "avatar": baixar(u["avatarUrl"]),
    }


def dados_demo(usuario):
    """Dados fictícios e estáveis, só para pré-visualizar o visual sem rede."""
    rnd = random.Random(42)
    hoje = dt.date.today()
    criado = hoje - dt.timedelta(days=560)
    dias = {}
    d = criado
    while d <= hoje:
        ativo = rnd.random() < (0.62 if d.weekday() < 5 else 0.3)
        dias[d] = int(rnd.expovariate(1 / 4)) + 1 if ativo else 0
        if rnd.random() < 0.03:
            dias[d] += rnd.randint(15, 30)
        d += dt.timedelta(days=1)
    for i in range(9):
        dias[hoje - dt.timedelta(days=i)] = max(dias[hoje - dt.timedelta(days=i)], rnd.randint(2, 9))
    linguagens = {"TypeScript": (620, "#3178c6"), "JavaScript": (140, "#f1e05a"),
                  "HTML": (100, "#e34c26"), "Python": (80, "#3572A5"),
                  "CSS": (35, "#663399"), "C#": (25, "#178600")}
    return {"login": usuario, "criado": criado, "hoje": hoje, "dias": dias, "repos": 28,
            "linguagens": linguagens, "avatar": None}


def estatisticas(dados):
    dias, hoje = dados["dias"], dados["hoje"]
    um_dia = dt.timedelta(days=1)

    maior, inicio_corrida, corrida = (0, None, None), None, 0
    d = min(dias) if dias else hoje
    while d <= hoje:
        if dias.get(d, 0) > 0:
            inicio_corrida = d if corrida == 0 else inicio_corrida
            corrida += 1
            if corrida > maior[0]:
                maior = (corrida, inicio_corrida, d)
        else:
            corrida = 0
        d += um_dia

    # A sequência atual não quebra só porque hoje ainda não houve contribuição.
    d = hoje if dias.get(hoje, 0) > 0 else hoje - um_dia
    atual = 0
    while dias.get(d, 0) > 0:
        atual += 1
        d -= um_dia

    ano = [(hoje - dt.timedelta(days=i), 0) for i in range(364, -1, -1)]
    ano = [(d, dias.get(d, 0)) for d, _ in ano]
    ativos = [c for _, c in ano if c > 0]
    melhor = max(ano, key=lambda x: x[1])
    return {
        "total": sum(dias.values()),
        "total_ano": sum(ativos),
        "dias_ativos": len(ativos),
        "media": sum(ativos) / len(ativos) if ativos else 0,
        "melhor": melhor,
        "atual": atual,
        "atual_desde": d + um_dia,
        "maior": maior,
        "ano": ano,
        "ultimos30": ano[-30:],
    }


# --------------------------------------------------------------- ASCII art

def ascii_de_imagem(conteudo, colunas, linhas):
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(conteudo)).convert("L")
    except Exception:
        return None
    w, h = img.size
    borda = ([img.getpixel((x, 0)) for x in range(w)] + [img.getpixel((x, h - 1)) for x in range(w)]
             + [img.getpixel((0, y)) for y in range(h)] + [img.getpixel((w - 1, y)) for y in range(h)])
    if sum(borda) / len(borda) > 127:
        img = ImageOps.invert(img)  # fundo claro vira espaço em branco no terminal
    caixa = img.point(lambda p: 255 if p > 48 else 0).getbbox()
    if caixa:
        x0, y0, x1, y1 = caixa
        lado = int(max(x1 - x0, y1 - y0) * 1.15)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        img = img.crop((cx - lado // 2, cy - lado // 2, cx + lado // 2, cy + lado // 2))
    # BOX faz a média dos pixels (sem serrilhado); o corte de 1% ignora artefatos de compressão.
    img = ImageOps.autocontrast(img.resize((colunas, linhas), Image.BOX), cutoff=1)
    passo = 256 / len(RAMPA)
    arte = ["".join(RAMPA[int(img.getpixel((x, y)) / passo)] for x in range(colunas)).rstrip()
            for y in range(linhas)]
    while arte and not arte[0]:
        arte.pop(0)
    while arte and not arte[-1]:
        arte.pop()
    return arte or None


# ------------------------------------------------------------- utilitários SVG

def num(n):
    return f"{n:,.0f}".replace(",", ".")


def data_br(d, ano=True):
    return f"{d.day} {MESES[d.month - 1]}" + (f" {d.year}" if ano else "")


def estilo(t):
    return f"""<style>
text {{ font-family: {FONTE}; fill: {t['texto']}; }}
.suave {{ fill: {t['suave']}; }}
.destaque {{ fill: {t['destaque']}; }}
.prompt {{ fill: {t['prompt']}; font-weight: 700; }}
.caminho {{ fill: {t['caminho']}; }}
.forte {{ font-weight: 700; }}
.surge {{ animation: surge .7s ease-out both; }}
.cursor {{ animation: pisca 1.1s steps(1) infinite; }}
.traco {{ stroke-dasharray: 1; animation: traco 1.8s ease-out both; }}
@keyframes surge {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@keyframes pisca {{ 50% {{ opacity: 0; }} }}
@keyframes traco {{ from {{ stroke-dashoffset: 1; }} to {{ stroke-dashoffset: 0; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>"""


def janela(t, altura, titulo, corpo):
    w = LARGURA
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{altura}" viewBox="0 0 {w} {altura}" role="img" aria-label="{escape(titulo)}">
{estilo(t)}
<rect x=".5" y=".5" width="{w - 1}" height="{altura - 1}" rx="12" fill="{t['fundo']}" stroke="{t['borda']}"/>
<path d="M12.5 .5H{w - 12.5}A12 12 0 0 1 {w - .5} 12.5V34.5H.5V12.5A12 12 0 0 1 12.5 .5Z" fill="{t['barra']}" stroke="{t['borda']}"/>
<circle cx="22" cy="17.5" r="6" fill="#ff5f57"/><circle cx="42" cy="17.5" r="6" fill="#febc2e"/><circle cx="62" cy="17.5" r="6" fill="#28c840"/>
<text x="{w / 2}" y="22" text-anchor="middle" font-size="12" class="suave">{escape(titulo)}</text>
{corpo}
</svg>
"""


def prompt(t, usuario, x, y, comando, digitar=False, cursor=False, ident="p"):
    """Linha 'usuario@github ~ $ comando', com efeito de digitação opcional."""
    fs = 14
    cw = fs * 0.6
    prefixo = f"{usuario}@github ~ $ "
    texto = (f'<text x="{x}" y="{y}" font-size="{fs}"><tspan class="prompt">{escape(usuario)}@github</tspan>'
             f'<tspan class="caminho"> ~</tspan><tspan class="suave"> $ </tspan>'
             f'<tspan>{escape(comando)}</tspan></text>')
    partes = []
    if digitar and comando:
        largs = [len(prefixo) * cw + i * cw for i in range(len(comando) + 1)]
        largs[-1] = LARGURA  # no fim, revela a linha inteira
        valores = ";".join(f"{v:.1f}" for v in largs)
        tempos = ";".join(f"{i / len(largs):.3f}" for i in range(len(largs)))
        partes.append(
            f'<clipPath id="{ident}"><rect x="{x - 2}" y="{y - fs - 4}" width="{LARGURA}" height="{fs + 10}">'
            f'<animate attributeName="width" values="{valores}" keyTimes="{tempos}" '
            f'dur="{len(largs) * 0.07:.2f}s" fill="freeze" calcMode="discrete"/></rect></clipPath>'
            f'<g clip-path="url(#{ident})">{texto}</g>')
    else:
        partes.append(texto)
    if cursor:
        cx = x + (len(prefixo) + len(comando)) * cw + 1
        partes.append(f'<rect class="cursor" x="{cx:.1f}" y="{y - fs + 2}" width="{cw:.1f}" height="{fs + 1}" fill="{t["destaque"]}"/>')
    return "\n".join(partes)


# ------------------------------------------------------------------- cards

def card_whoami(t, dados, est, arte):
    usuario = dados["login"].lower()
    p = [prompt(t, usuario, 24, 64, "whoami", digitar=True, ident="pw")]

    # avatar em ASCII, à esquerda
    fs, lh = 12, 13
    topo = 92
    linhas = [escape(l).replace(" ", NBSP) for l in arte]
    tspans = "".join(f'<tspan x="24" dy="{0 if i == 0 else lh}">{l or NBSP}</tspan>' for i, l in enumerate(linhas))
    largura_arte = max((len(l) for l in arte), default=0) * fs * 0.6
    altura_arte = len(arte) * lh
    desloc_y = max(0, (286 - altura_arte) / 2)
    p.append(f'<g class="surge" style="animation-delay:.5s"><text y="{topo + desloc_y:.1f}" font-size="{fs}" '
             f'class="destaque forte" style="white-space:pre">{tspans}</text></g>')

    # apresentação e números, à direita
    x0 = max(330, 24 + largura_arte + 36)
    larg = LARGURA - 24 - x0
    y = topo + 14
    bloco = [f'<text x="{x0}" y="{y}" font-size="24" class="forte">{escape(PERFIL["nome"])}</text>',
             f'<text x="{x0}" y="{y + 26}" font-size="14" class="destaque">{escape(PERFIL["cargo"])}</text>']
    for i, linha in enumerate(PERFIL["bio"]):
        bloco.append(f'<text x="{x0}" y="{y + 52 + i * 19}" font-size="13" class="suave">{escape(linha)}</text>')
    y = y + 52 + len(PERFIL["bio"]) * 19 + 8

    itens = [
        (num(est["total_ano"]), "contribuições (12 meses)"),
        (num(est["dias_ativos"]), "dias ativos (12 meses)"),
        (num(est["melhor"][1]), f"melhor dia · {data_br(est['melhor'][0], False)}"),
        (f"{est['media']:.1f}".replace(".", ","), "média por dia ativo"),
        (num(dados["repos"]), "repositórios públicos"),
        (num(len(dados["linguagens"])), "linguagens no código"),
    ]
    gap = 10
    cw = (larg - 2 * gap) / 3
    ch = 56
    for i, (valor, rotulo) in enumerate(itens):
        cx = x0 + (i % 3) * (cw + gap)
        cy = y + (i // 3) * (ch + gap)
        bloco.append(
            f'<rect x="{cx:.1f}" y="{cy}" width="{cw:.1f}" height="{ch}" rx="8" fill="{t["caixa"]}" stroke="{t["borda"]}"/>'
            f'<text x="{cx + 12:.1f}" y="{cy + 26}" font-size="19" class="destaque forte">{escape(valor)}</text>'
            f'<text x="{cx + 12:.1f}" y="{cy + 45}" font-size="11" class="suave">{escape(rotulo)}</text>')
    y += 2 * ch + gap + 26

    # barra de linguagens
    total = sum(tam for tam, _ in dados["linguagens"].values()) or 1
    top = sorted(dados["linguagens"].items(), key=lambda kv: -kv[1][0])[:5]
    resto = total - sum(tam for _, (tam, _) in top)
    if resto > 0:
        top.append(("Outras", (resto, t["suave"])))
    bloco.append(f'<text x="{x0}" y="{y}" font-size="11" class="suave">linguagens (repositórios públicos)</text>')
    y += 10
    bloco.append(f'<clipPath id="bl"><rect x="{x0}" y="{y}" width="{larg}" height="8" rx="4"/></clipPath><g clip-path="url(#bl)">')
    xx = x0
    for nome, (tam, cor) in top:
        lw = larg * tam / total
        bloco.append(f'<rect x="{xx:.1f}" y="{y}" width="{lw + .5:.1f}" height="8" fill="{cor}"/>')
        xx += lw
    bloco.append("</g>")
    y += 26
    xx = x0
    for nome, (tam, cor) in top:
        rot = f"{nome} {100 * tam / total:.0f}%"
        largura_rot = 13 + len(rot) * 6.6
        if xx > x0 and xx + largura_rot > LARGURA - 24:
            xx, y = x0, y + 20
        bloco.append(f'<circle cx="{xx + 4}" cy="{y - 4}" r="4" fill="{cor}"/>'
                     f'<text x="{xx + 13}" y="{y}" font-size="11" class="suave">{escape(rot)}</text>')
        xx += largura_rot + 14
    p.append(f'<g class="surge" style="animation-delay:.8s">{"".join(bloco)}</g>')

    altura = int(max(y, topo + 286)) + 26
    return janela(t, altura, f"{usuario}@github: ~", "\n".join(p))


def anel_chama(t, cx, cy):
    return (f'<circle cx="{cx}" cy="{cy}" r="11" fill="{t["fundo"]}"/>'
            f'<path transform="translate({cx} {cy})" fill="{t["destaque"]}" '
            f'd="M0-8C3.5-4.5 6-1.5 6 2.5C6 6 3.3 8.5 0 8.5S-6 6-6 2.5C-6 0-4.5-2-3-3.5C-3-1.5-2 0-.8.5C-1.3-3.5-.5-6 0-8Z"/>')


def card_analytics(t, dados, est):
    usuario = dados["login"].lower()
    p = [prompt(t, usuario, 24, 64, "./analytics.sh", digitar=True, ident="pa")]

    colunas = [150, 450, 750]
    for x in (300, 600):
        p.append(f'<path d="M{x} 96V214" stroke="{t["borda"]}"/>')

    maior_n, maior_ini, maior_fim = est["maior"]
    total = (f'<text x="{colunas[0]}" y="150" text-anchor="middle" font-size="32" class="forte">{num(est["total"])}</text>'
             f'<text x="{colunas[0]}" y="180" text-anchor="middle" font-size="13" class="destaque">Total de contribuições</text>'
             f'<text x="{colunas[0]}" y="200" text-anchor="middle" font-size="11" class="suave">{data_br(dados["criado"])} – hoje</text>')
    cx, cy = colunas[1], 138
    atual = (f'<circle cx="{cx}" cy="{cy}" r="38" fill="none" stroke="{t["borda"]}" stroke-width="5"/>'
             f'<circle class="traco" pathLength="1" cx="{cx}" cy="{cy}" r="38" fill="none" stroke="{t["destaque"]}" '
             f'stroke-width="5" stroke-linecap="round" transform="rotate(-90 {cx} {cy})"/>'
             + anel_chama(t, cx, cy - 38) +
             f'<text x="{cx}" y="{cy + 10}" text-anchor="middle" font-size="28" class="forte">{est["atual"]}</text>'
             f'<text x="{cx}" y="{cy + 64}" text-anchor="middle" font-size="13" class="destaque">Sequência atual</text>'
             f'<text x="{cx}" y="{cy + 82}" text-anchor="middle" font-size="11" class="suave">'
             f'{"desde " + data_br(est["atual_desde"], False) if est["atual"] else "comece hoje!"}</text>')
    periodo = f"{data_br(maior_ini, False)} – {data_br(maior_fim)}" if maior_n else "—"
    maior = (f'<text x="{colunas[2]}" y="150" text-anchor="middle" font-size="32" class="forte">{maior_n}</text>'
             f'<text x="{colunas[2]}" y="180" text-anchor="middle" font-size="13" class="destaque">Maior sequência</text>'
             f'<text x="{colunas[2]}" y="200" text-anchor="middle" font-size="11" class="suave">{periodo}</text>')
    p.append(f'<g class="surge" style="animation-delay:.6s">{total}{atual}{maior}</g>')

    # gráfico dos últimos 30 dias
    x0, x1, y0, y1 = 64, LARGURA - 32, 282, 392
    serie = est["ultimos30"]
    pico = max(max(c for _, c in serie), 1)
    passo = (x1 - x0) / (len(serie) - 1)
    pts = [(x0 + i * passo, y1 - (y1 - y0) * c / pico) for i, (_, c) in enumerate(serie)]
    g = [f'<text x="{LARGURA / 2}" y="252" text-anchor="middle" font-size="12" class="suave">atividade · últimos 30 dias</text>']
    for frac in (0, .5, 1):
        yy = y1 - (y1 - y0) * frac
        g.append(f'<path d="M{x0} {yy:.1f}H{x1}" stroke="{t["borda"]}" stroke-dasharray="3 4"/>'
                 f'<text x="{x0 - 10}" y="{yy + 4:.1f}" text-anchor="end" font-size="10" class="suave">{round(pico * frac)}</text>')
    for i, (d, _) in enumerate(serie):
        if i % 5 == 0 or i == len(serie) - 1:
            g.append(f'<text x="{x0 + i * passo:.1f}" y="{y1 + 18}" text-anchor="middle" font-size="10" class="suave">{d.day:02d}/{d.month:02d}</text>')
    linha = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    area = linha + f" L{x1} {y1} L{x0} {y1}Z"
    g.append(f'<defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="{t["destaque"]}" stop-opacity=".35"/>'
             f'<stop offset="1" stop-color="{t["destaque"]}" stop-opacity="0"/></linearGradient></defs>'
             f'<path d="{area}" fill="url(#ga)" class="surge" style="animation-delay:1s"/>'
             f'<path class="traco" pathLength="1" d="{linha}" fill="none" stroke="{t["destaque"]}" '
             f'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" style="animation-delay:.6s"/>')
    g.append('<g class="surge" style="animation-delay:1.4s">' + "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{t["fundo"]}" stroke="{t["destaque"]}" stroke-width="1.6"/>'
        for x, y in pts) + "</g>")
    p.append("".join(g))
    return janela(t, 432, f"{usuario}@github: ~/analytics", "\n".join(p))


def card_contribuicoes(t, dados, est):
    usuario = dados["login"].lower()
    p = [prompt(t, usuario, 24, 64, "./contribuicoes.sh", digitar=True, ident="pc")]

    ano = est["ano"]
    # Colunas = semanas começando no domingo, como no GitHub.
    inicio = ano[0][0] - dt.timedelta(days=(ano[0][0].weekday() + 1) % 7)
    contagem = dict(ano)
    positivos = sorted(c for _, c in ano if c > 0)

    def nivel(c):
        if c <= 0 or not positivos:
            return 0
        for i, q in enumerate((.25, .5, .75), start=1):
            if c <= positivos[int(q * (len(positivos) - 1))]:
                return i
        return 4

    cel, gap = 12, 3
    x0, y0 = 58, 104
    semanas = (ano[-1][0] - inicio).days // 7 + 1
    grade = []
    mes_anterior = None
    for s in range(semanas):
        x = x0 + s * (cel + gap)
        dia1 = inicio + dt.timedelta(days=7 * s)
        if dia1.month != mes_anterior and s < semanas - 2:
            grade.append(f'<text x="{x}" y="{y0 - 10}" font-size="10" class="suave">{MESES[dia1.month - 1]}</text>')
            mes_anterior = dia1.month
        quadrados = []
        for dsem in range(7):
            d = dia1 + dt.timedelta(days=dsem)
            if d not in contagem:
                continue
            c = contagem[d]
            quadrados.append(f'<rect x="{x}" y="{y0 + dsem * (cel + gap)}" width="{cel}" height="{cel}" rx="2.5" '
                             f'fill="{t["niveis"][nivel(c)]}"><title>{c} em {data_br(d)}</title></rect>')
        grade.append(f'<g class="surge" style="animation-delay:{.4 + s * .018:.3f}s">{"".join(quadrados)}</g>')
    for dsem, rot in ((1, "seg"), (3, "qua"), (5, "sex")):
        grade.append(f'<text x="24" y="{y0 + dsem * (cel + gap) + 10}" font-size="10" class="suave">{rot}</text>')
    p.append("".join(grade))

    yl = y0 + 7 * (cel + gap) + 22
    p.append(f'<text x="24" y="{yl}" font-size="12" class="suave"><tspan class="destaque forte">{num(est["total_ano"])}</tspan>'
             f' contribuições nos últimos 12 meses</text>')
    xl = LARGURA - 24 - 5 * (cel + gap) - 36
    leg = [f'<text x="{xl - 8}" y="{yl}" text-anchor="end" font-size="10" class="suave">menos</text>']
    for i, cor in enumerate(t["niveis"]):
        leg.append(f'<rect x="{xl + i * (cel + gap)}" y="{yl - 10}" width="{cel}" height="{cel}" rx="2.5" fill="{cor}"/>')
    leg.append(f'<text x="{xl + 5 * (cel + gap) + 4}" y="{yl}" font-size="10" class="suave">mais</text>')
    p.append("".join(leg))
    p.append(prompt(t, usuario, 24, yl + 34, "", cursor=True))
    return janela(t, int(yl + 56), f"{usuario}@github: ~/contribuicoes", "\n".join(p))


def card_cobrinha(t, usuario, svg_cobra):
    """Coloca o SVG gerado pelo Platane/snk dentro de uma janela de terminal."""
    texto = re.sub(r"<\?xml[^>]*\?>", "", svg_cobra).strip()
    m = re.match(r"<svg\b([^>]*)>", texto)
    if not m:
        return None
    atributos = m.group(1)
    vb = re.search(r'viewBox="([^"]+)"', atributos)
    if vb:
        caixa = [float(v) for v in vb.group(1).replace(",", " ").split()]
    else:
        w = re.search(r'\swidth="([\d.]+)', atributos)
        h = re.search(r'\sheight="([\d.]+)', atributos)
        if not (w and h):
            return None
        caixa = [0, 0, float(w.group(1)), float(h.group(1))]
        atributos += f' viewBox="0 0 {caixa[2]} {caixa[3]}"'
    atributos = re.sub(r'\s(width|height|x|y)="[^"]*"', "", atributos)
    larg = LARGURA - 48
    alt = larg * caixa[3] / caixa[2]
    aninhado = f'<svg x="24" y="84" width="{larg}" height="{alt:.1f}"{atributos}>' + texto[m.end():]
    corpo = prompt(t, usuario, 24, 64, "./cobrinha.sh", digitar=True, ident="pk") + "\n" + aninhado
    return janela(t, int(84 + alt + 20), f"{usuario}@github: ~/cobrinha", corpo)


# --------------------------------------------------------------------- main

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Gera os cards SVG do README de perfil.")
    ap.add_argument("--usuario", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "Corrar"))
    ap.add_argument("--tema", choices=sorted(TEMAS), default="verde")
    ap.add_argument("--saida", default="dist")
    ap.add_argument("--imagem", help="imagem usada no ASCII no lugar do avatar do GitHub")
    ap.add_argument("--demo", action="store_true", help="usa dados fictícios (sem rede)")
    ap.add_argument("--cobra", help="SVG gerado pelo Platane/snk, para colocar na janela de terminal")
    args = ap.parse_args()

    if args.demo:
        dados = dados_demo(args.usuario)
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise SystemExit("Defina GITHUB_TOKEN (na Action ele já existe) ou use --demo.")
        dados = buscar(args.usuario, token)

    imagem = Path(args.imagem).read_bytes() if args.imagem else dados["avatar"]
    arte = (ascii_de_imagem(imagem, 40, 21) if imagem else None) or ASCII_RESERVA

    t = TEMAS[args.tema]
    est = estatisticas(dados)
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    cards = {
        "whoami.svg": card_whoami(t, dados, est, arte),
        "analytics.svg": card_analytics(t, dados, est),
        "contribuicoes.svg": card_contribuicoes(t, dados, est),
    }
    if args.cobra and Path(args.cobra).exists():
        cobra = card_cobrinha(t, dados["login"].lower(), Path(args.cobra).read_text(encoding="utf-8"))
        # Se o formato do snk mudar, publica a cobrinha original para o README não quebrar.
        cards["cobrinha.svg"] = cobra or Path(args.cobra).read_text(encoding="utf-8")
    for nome, svg in cards.items():
        (saida / nome).write_text(svg, encoding="utf-8")
        print(f"ok  {saida / nome}")
    print(f"{num(est['total'])} contribuições no total · sequência atual {est['atual']} · maior {est['maior'][0]}")


if __name__ == "__main__":
    main()
