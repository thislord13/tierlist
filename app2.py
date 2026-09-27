import copy
import random
import secrets
import string
from datetime import datetime

from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex(24)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
rooms = {}


def make_property(name, color, price, rent, house_price):
    return {
        "name": name,
        "type": "property",
        "color": color,
        "price": price,
        "rent": rent,
        "house_price": house_price,
        "owner": None,
        "houses": 0,
        "hotel": False,
    }


def make_special(name, kind, **details):
    return {"name": name, "type": kind, **details}


BOARD = [
    make_special("Partida", "go"),
    make_property("Rio de Janeiro · Copacabana", "brown", 60, 2, 50),
    make_special("Caixa da comunidade", "community"),
    make_property("Ipanema", "brown", 60, 4, 50),
    make_special("Imposto de renda", "tax", amount=200),
    make_special("Estação Central", "railroad", price=200, rent=25, owner=None),
    make_property("São Paulo · Paulista", "lightblue", 100, 6, 50),
    make_special("Sorte", "chance"),
    make_property("Liberdade", "lightblue", 100, 6, 50),
    make_property("Jardins", "lightblue", 120, 8, 50),
    make_special("Prisão / visita", "jail"),
    make_property("Las Vegas Strip", "pink", 140, 10, 100),
    make_special("Companhia de energia", "utility", price=150, owner=None),
    make_property("Bellagio", "pink", 140, 10, 100),
    make_property("Fremont Street", "pink", 160, 12, 100),
    make_special("Estação do Aeroporto", "railroad", price=200, rent=25, owner=None),
    make_property("Hollywood", "orange", 180, 14, 100),
    make_special("Caixa da comunidade", "community"),
    make_property("Beverly Hills", "orange", 180, 14, 100),
    make_property("Sunset Boulevard", "orange", 200, 16, 100),
    make_special("Estacionamento livre", "free"),
    make_property("Piccadilly Circus", "red", 220, 18, 150),
    make_special("Sorte", "chance"),
    make_property("Champs-Élysées", "red", 220, 18, 150),
    make_property("Avenida Montaigne", "red", 240, 20, 150),
    make_special("Estação de Shinkansen", "railroad", price=200, rent=25, owner=None),
    make_property("Shibuya", "yellow", 260, 22, 150),
    make_property("Shinjuku", "yellow", 260, 22, 150),
    make_special("Companhia de água", "utility", price=150, owner=None),
    make_property("Ginza", "yellow", 280, 24, 150),
    make_special("Vá para a prisão", "go_to_jail"),
    make_property("Dubai Marina", "green", 300, 26, 200),
    make_property("Palm Jumeirah", "green", 300, 26, 200),
    make_special("Caixa da comunidade", "community"),
    make_property("Burj Khalifa", "green", 320, 28, 200),
    make_special("Estação de Waterloo", "railroad", price=200, rent=25, owner=None),
    make_special("Sorte", "chance"),
    make_property("Fifth Avenue", "darkblue", 350, 35, 200),
    make_special("Imposto de luxo", "tax", amount=100),
    make_property("Times Square", "darkblue", 400, 50, 200),
]

PLAYER_COLORS = ["#f05a61", "#53b8f3", "#e9b949", "#bb83ea"]

CHALLENGES = [
    {"q": "Ao completar um grupo de cor, qual construção fica disponível?", "a": ["Casas", "Somente estações", "Nenhuma construção"], "correct": 0},
    {"q": "Qual é o valor recebido ao passar pela Partida?", "a": ["M$ 100", "M$ 200", "M$ 500"], "correct": 1},
    {"q": "Quantas casas cabem em uma rua antes da evolução para complexo?", "a": ["Duas", "Quatro", "Seis"], "correct": 1},
    {"q": "O que acontece com o aluguel de uma propriedade hipotecada?", "a": ["Não é cobrado enquanto estiver hipotecada", "É sempre dobrado", "Vai para o centro do tabuleiro"], "correct": 0},
    {"q": "Quantos lançamentos duplos seguidos mandam um jogador para a prisão?", "a": ["Dois", "Três", "Quatro"], "correct": 1},
    {"q": "O que é necessário para construir casas em uma rua?", "a": ["Ter o grupo de cor completo", "Ter passado duas vezes pela Partida", "Possuir uma estação"], "correct": 0},
    {"q": "Parar no estacionamento livre rende um prêmio em dinheiro?", "a": ["Sim, M$ 200", "Sim, o valor dos impostos", "Não, é apenas uma parada livre"], "correct": 2},
    {"q": "Ao cair em uma propriedade sem dono, o jogador pode comprá-la?", "a": ["Sim, pagando o preço indicado", "Só depois de uma volta completa", "Não, apenas o banqueiro pode"], "correct": 0},
    {"q": "Se a dívida não puder ser paga, qual é o resultado previsto nas regras?", "a": ["O jogador continua sem pagar", "O jogador sai da partida", "Todos dividem a dívida"], "correct": 1},
    {"q": "Como os hotéis/complexos são construídos nesta versão das regras?", "a": ["Depois de quatro casas na rua", "Antes da primeira casa", "Somente em estações"], "correct": 0},
    {"q": "Qual é o valor inicial por jogador indicado no arquivo de regras?", "a": ["M$ 1.000", "M$ 1.500", "M$ 2.000"], "correct": 1},
    {"q": "Quando alguém recusa comprar uma propriedade livre, a regra tradicional prevê o quê?", "a": ["Leilão entre jogadores", "Propriedade removida", "Aluguel imediato"], "correct": 0},
]


def create_room_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if code not in rooms:
            return code


def player_for_sid(sid):
    for room in rooms.values():
        for player in room["players"].values():
            if player.get("sid") == sid:
                return room, player
    return None, None


def room_payload(room):
    return {
        "code": room["code"],
        "host": room["host"],
        "started": room["started"],
        "players": [
            {
                "id": player["id"],
                "name": player["name"],
                "color": player["color"],
                "connected": player["connected"],
                "bankrupt": player.get("bankrupt", False),
            }
            for player in room["players"].values()
        ],
    }


def game_payload(room):
    game = room["game"]
    if game is None:
        return None
    challenge = game["challenge"]
    return {
        "code": room["code"],
        "players": [
            {
                key: player[key]
                for key in (
                    "id", "name", "color", "connected", "money", "pos",
                    "properties", "jailed", "bankrupt",
                )
            }
            for player in room["players"].values()
        ],
        "board": game["board"],
        "current": game["current"],
        "has_rolled": game["has_rolled"],
        "pending_buy": game["pending_buy"],
        "pending_landing": game["pending_landing"],
        "dice": game["dice"],
        "log": game["log"],
        "phase": game["phase"],
        "winner": game.get("winner"),
        "challenge": (
            {
                "q": challenge["q"],
                "a": challenge["a"],
                "player": challenge["player"],
                "kind": challenge["kind"],
                "purpose": challenge["purpose"],
                "rent": challenge.get("rent"),
            }
            if challenge
            else None
        ),
    }


def broadcast_room(room):
    payload = room_payload(room)
    socketio.emit("room_update", payload, to=room["code"])
    if room["started"]:
        socketio.emit("game_state", game_payload(room), to=room["code"])


def send_chat_history(room):
    emit(
        "chat_history",
        {"messages": room["chat"]},
        to=request.sid,
    )


def emit_error(message):
    emit("game_error", {"message": message}, to=request.sid)


def next_turn(room):
    game = room["game"]
    game["has_rolled"] = False
    game["pending_buy"] = None
    game["pending_landing"] = None
    game["challenge"] = None
    order = room["order"]
    if not order:
        return
    try:
        current_index = order.index(game["current"])
    except ValueError:
        current_index = -1
    for offset in range(1, len(order) + 1):
        candidate = order[(current_index + offset) % len(order)]
        player = room["players"].get(candidate)
        if player and player["connected"] and not player["bankrupt"]:
            game["current"] = candidate
            game["log"] = f"É a vez de {player['name']}."
            return
    game["log"] = "Aguardando um jogador reconectar."


def finish_if_bankrupt(room):
    game = room["game"]
    active = [
        player for player in room["players"].values()
        if not player["bankrupt"]
    ]
    if len(active) <= 1:
        game["phase"] = "finished"
        game["pending_buy"] = None
        game["challenge"] = None
        game["winner"] = active[0]["id"] if active else None
        game["log"] = (
            f"{active[0]['name']} venceu a partida!"
            if active
            else "Todos os jogadores faliram."
        )
        return True
    return False


def charge_player(room, player, amount, recipient=None):
    if player["money"] < amount:
        player["money"] = 0
        player["bankrupt"] = True
        for index in player["properties"]:
            space = room["game"]["board"][index]
            space["owner"] = None
            space["houses"] = 0
            space["hotel"] = False
        player["properties"] = []
        room["game"]["log"] = f"{player['name']} faliu; suas propriedades voltaram ao banco."
        if not finish_if_bankrupt(room):
            message = room["game"]["log"]
            next_turn(room)
            room["game"]["log"] = f"{message} É a vez de {room['players'][room['game']['current']]['name']}."
        return False
    player["money"] -= amount
    if recipient:
        recipient["money"] += amount
    return True


def remove_lobby_player(room, player):
    player_id = player["id"]
    room["players"].pop(player_id)
    room["order"].remove(player_id)
    for token, owner_id in list(room["tokens"].items()):
        if owner_id == player_id:
            room["tokens"].pop(token)
    if room["host"] == player_id and room["players"]:
        connected = [
            key for key, other in room["players"].items()
            if other["connected"]
        ]
        room["host"] = connected[0] if connected else next(iter(room["players"]))
    for index, remaining in enumerate(room["players"].values()):
        remaining["color"] = PLAYER_COLORS[index]


@socketio.on("create_room")
def create_room(data):
    data = data if isinstance(data, dict) else {}
    name = (data.get("name") or "").strip()[:18]
    if not name:
        emit_error("Digite seu nome para criar uma sala.")
        return
    code = create_room_code()
    player_id = secrets.token_hex(8)
    token = secrets.token_urlsafe(32)
    player = {
        "id": player_id,
        "sid": request.sid,
        "name": name,
        "color": PLAYER_COLORS[0],
        "connected": True,
        "money": 1500,
        "pos": 0,
        "properties": [],
        "jailed": False,
        "bankrupt": False,
    }
    rooms[code] = {
        "code": code,
        "host": player_id,
        "players": {player_id: player},
        "tokens": {token: player_id},
        "order": [player_id],
        "chat": [],
        "started": False,
        "game": None,
    }
    join_room(code)
    emit("room_joined", {"code": code, "token": token, "player_id": player_id})
    send_chat_history(rooms[code])
    broadcast_room(rooms[code])


@socketio.on("join_room")
def join_game_room(data):
    data = data if isinstance(data, dict) else {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()[:18]
    room = rooms.get(code)
    if not name:
        emit_error("Digite seu nome para entrar na sala.")
        return
    if not room:
        emit_error("Não encontramos uma sala com esse código.")
        return
    if room["started"]:
        emit_error("Essa partida já começou e não aceita novos jogadores.")
        return
    if len(room["players"]) >= 4:
        for offline_id in [
            player_id for player_id, player in room["players"].items()
            if not player["connected"]
        ]:
            room["players"].pop(offline_id)
            room["order"].remove(offline_id)
            for token, owner_id in list(room["tokens"].items()):
                if owner_id == offline_id:
                    room["tokens"].pop(token)
            if len(room["players"]) < 4:
                break
        for index, remaining in enumerate(room["players"].values()):
            remaining["color"] = PLAYER_COLORS[index]
    if len(room["players"]) >= 4:
        emit_error("A sala já está completa (máximo de 4 jogadores).")
        return
    player_id = secrets.token_hex(8)
    token = secrets.token_urlsafe(32)
    player = {
        "id": player_id,
        "sid": request.sid,
        "name": name,
        "color": PLAYER_COLORS[len(room["players"])],
        "connected": True,
        "money": 1500,
        "pos": 0,
        "properties": [],
        "jailed": False,
        "bankrupt": False,
    }
    room["players"][player_id] = player
    room["tokens"][token] = player_id
    room["order"].append(player_id)
    if not room["players"].get(room["host"], {}).get("connected"):
        room["host"] = player_id
    join_room(code)
    emit("room_joined", {"code": code, "token": token, "player_id": player_id})
    send_chat_history(room)
    broadcast_room(room)


@socketio.on("rejoin_room")
def rejoin_game_room(data):
    data = data if isinstance(data, dict) else {}
    code = (data.get("code") or "").strip().upper()
    token = data.get("token")
    room = rooms.get(code)
    player_id = room["tokens"].get(token) if room and isinstance(token, str) else None
    player = room["players"].get(player_id) if room and player_id else None
    if not room or not player:
        emit_error("A sala ou a sessão anterior não está mais disponível. Crie ou entre em outra sala.")
        emit("session_expired", to=request.sid)
        return
    player["sid"] = request.sid
    player["connected"] = True
    if room["started"]:
        current = room["players"].get(room["game"]["current"])
        if not current or not current["connected"] or current["bankrupt"]:
            next_turn(room)
    join_room(code)
    emit("room_joined", {"code": code, "token": token, "player_id": player_id})
    send_chat_history(room)
    broadcast_room(room)


@socketio.on("chat_send")
def chat_send(data):
    room, player = player_for_sid(request.sid)
    if not room or not player or not player["connected"]:
        emit_error("Entre em uma sala para enviar mensagens.")
        return
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, str) or not message.strip():
        emit_error("Digite uma mensagem antes de enviar.")
        return
    entry = {
        "name": player["name"],
        "color": player["color"],
        "message": message.strip()[:500],
        "time": datetime.now().strftime("%H:%M"),
    }
    room["chat"].append(entry)
    del room["chat"][:-100]
    socketio.emit("chat_message", entry, to=room["code"])


@socketio.on("start_game")
def start_game():
    room, player = player_for_sid(request.sid)
    if not room or not player:
        emit_error("Entre em uma sala antes de iniciar.")
        return
    if room["host"] != player["id"]:
        emit_error("Somente quem criou a sala pode iniciar a partida.")
        return
    if room["started"]:
        emit_error("A partida já foi iniciada.")
        return
    online_players = [
        player for player in room["players"].values()
        if player["connected"]
    ]
    if not 2 <= len(online_players) <= 4:
        emit_error("São necessários de 2 a 4 jogadores conectados.")
        return
    for player_id in list(room["players"]):
        if not room["players"][player_id]["connected"]:
            room["players"].pop(player_id)
            room["order"].remove(player_id)
            for token, owner_id in list(room["tokens"].items()):
                if owner_id == player_id:
                    room["tokens"].pop(token)
    for index, player in enumerate(room["players"].values()):
        player["color"] = PLAYER_COLORS[index]
    room["started"] = True
    room["game"] = {
        "board": copy.deepcopy(BOARD),
        "current": room["order"][0],
        "has_rolled": False,
        "pending_buy": None,
        "pending_landing": None,
        "dice": [1, 1],
        "log": "Partida iniciada! Boa sorte.",
        "phase": "playing",
        "winner": None,
        "challenge": None,
    }
    for player in room["players"].values():
        player.update(money=1500, pos=0, properties=[], jailed=False, bankrupt=False)
    broadcast_room(room)


@socketio.on("monopoly_roll")
def monopoly_roll():
    room, player = player_for_sid(request.sid)
    if not room or not room["started"]:
        emit_error("Entre em uma partida antes de rolar os dados.")
        return
    game = room["game"]
    if game["phase"] != "playing" or game["current"] != player["id"]:
        emit_error("Não é sua vez.")
        return
    if game["has_rolled"] or game["challenge"] or game["pending_landing"] or game["pending_buy"] is not None:
        emit_error("Encerre sua jogada atual antes de rolar novamente.")
        return
    if player["jailed"]:
        if charge_player(room, player, 50):
            player["jailed"] = False
            game["log"] = f"{player['name']} pagou M$ 50 para sair da prisão."
            next_turn(room)
        broadcast_room(room)
        return
    dice = [random.randint(1, 6), random.randint(1, 6)]
    game["dice"] = dice
    game["has_rolled"] = True
    old_position = player["pos"]
    player["pos"] = (old_position + sum(dice)) % len(game["board"])
    if player["pos"] < old_position or player["pos"] == 0:
        player["money"] += 200
    space = game["board"][player["pos"]]
    game["log"] = f"{player['name']} tirou {dice[0]} + {dice[1]} e chegou a {space['name']}."
    if space["type"] in ("property", "railroad", "utility"):
        if space["owner"] is None:
            game["pending_buy"] = player["pos"]
            game["log"] = f"{player['name']} chegou a {space['name']}, disponível por M$ {space['price']}."
        elif space["owner"] != player["id"]:
            owner = room["players"].get(space["owner"])
            if owner and not owner["bankrupt"]:
                rent = space.get("rent", 0)
                if space["type"] == "railroad":
                    count = sum(
                        game["board"][index]["type"] == "railroad"
                        for index in owner["properties"]
                    )
                    rent = 25 * (2 ** max(0, count - 1))
                elif space["type"] == "utility":
                    count = sum(
                        game["board"][index]["type"] == "utility"
                        for index in owner["properties"]
                    )
                    rent = sum(dice) * (10 if count == 2 else 4)
                else:
                    group = [
                        item for item in game["board"]
                        if item["type"] == "property" and item["color"] == space["color"]
                    ]
                    if space["hotel"]:
                        rent *= 12
                    elif space["houses"]:
                        rent *= (space["houses"] + 1) * 2
                    elif all(item["owner"] == owner["id"] for item in group):
                        rent *= 2
                game["pending_landing"] = {
                    "kind": "rent",
                    "player": player["id"],
                    "owner": owner["id"],
                    "space": player["pos"],
                    "amount": rent,
                }
                game["log"] = f"{player['name']} deve M$ {rent} de aluguel para {owner['name']} ou pode tentar um desafio."
    elif space["type"] == "tax":
        if charge_player(room, player, space["amount"]):
            game["log"] = f"{player['name']} pagou M$ {space['amount']} de imposto."
    elif space["type"] in ("chance", "community"):
        challenge = copy.deepcopy(random.choice(CHALLENGES))
        game["challenge"] = {
            **challenge,
            "player": player["id"],
            "kind": space["type"],
            "purpose": "card",
        }
    elif space["type"] == "go_to_jail":
        player["pos"] = 10
        player["jailed"] = True
        game["log"] = f"{player['name']} foi enviado à prisão e perderá a próxima vez, ou poderá pagar M$ 50 para sair."
    elif space["type"] == "free":
        game["log"] = f"{player['name']} parou no estacionamento livre. Sem bônus."
    elif space["type"] == "jail":
        game["log"] = f"{player['name']} está apenas de visita à prisão."
    broadcast_room(room)


@socketio.on("monopoly_pay_rent")
def monopoly_pay_rent():
    room, player = player_for_sid(request.sid)
    if not room or not room["started"]:
        emit_error("Entre em uma partida antes de pagar.")
        return
    game = room["game"]
    landing = game["pending_landing"]
    if (
        game["phase"] != "playing"
        or not landing
        or landing["player"] != player["id"]
        or game["current"] != player["id"]
    ):
        emit_error("Não há um aluguel aguardando seu pagamento.")
        return
    owner = room["players"].get(landing["owner"])
    if not owner or owner["bankrupt"]:
        game["pending_landing"] = None
        game["log"] = "O proprietário não está mais na partida; nenhum aluguel é devido."
    else:
        game["pending_landing"] = None
        if charge_player(room, player, landing["amount"], owner):
            game["log"] = f"{player['name']} pagou M$ {landing['amount']} de aluguel para {owner['name']}."
    broadcast_room(room)


@socketio.on("monopoly_rent_challenge")
def monopoly_rent_challenge():
    room, player = player_for_sid(request.sid)
    if not room or not room["started"]:
        emit_error("Entre em uma partida antes de escolher um desafio.")
        return
    game = room["game"]
    landing = game["pending_landing"]
    if (
        game["phase"] != "playing"
        or not landing
        or landing["player"] != player["id"]
        or game["current"] != player["id"]
    ):
        emit_error("Não há uma propriedade aguardando sua decisão.")
        return
    challenge = copy.deepcopy(random.choice(CHALLENGES))
    game["challenge"] = {
        **challenge,
        "player": player["id"],
        "kind": "rent",
        "purpose": "rent",
        "rent": landing["amount"],
        "owner": landing["owner"],
    }
    game["pending_landing"] = None
    game["log"] = f"{player['name']} escolheu tentar um desafio para escapar do aluguel."
    broadcast_room(room)


@socketio.on("monopoly_challenge_answer")
def monopoly_challenge_answer(data):
    room, player = player_for_sid(request.sid)
    if not room or not room["started"]:
        emit_error("Entre em uma partida antes de responder.")
        return
    challenge = room["game"]["challenge"]
    if room["game"]["phase"] != "playing" or player["bankrupt"] or not challenge or challenge["player"] != player["id"]:
        emit_error("Não há uma carta aguardando sua resposta.")
        return
    answer = data.get("answer") if isinstance(data, dict) else None
    if not isinstance(answer, int) or not 0 <= answer < len(challenge["a"]):
        emit_error("Escolha uma das respostas da carta.")
        return
    if challenge["purpose"] == "rent":
        owner = room["players"].get(challenge["owner"])
        if answer == challenge["correct"]:
            room["game"]["log"] = f"Resposta certa! {player['name']} escapou do aluguel."
            room["game"]["challenge"] = None
        elif owner and not owner["bankrupt"]:
            charge_player(room, player, challenge["rent"], owner)
            if room["game"]["phase"] == "playing":
                room["game"]["log"] = f"Resposta incorreta. {player['name']} pagou M$ {challenge['rent']} de aluguel."
                room["game"]["challenge"] = None
        else:
            room["game"]["log"] = "O proprietário não está mais na partida; nenhum aluguel é devido."
            room["game"]["challenge"] = None
    elif answer == challenge["correct"]:
        player["money"] += 100
        room["game"]["log"] = f"Resposta certa! {player['name']} ganhou M$ 100."
        room["game"]["challenge"] = None
    else:
        charge_player(room, player, 50)
        if room["game"]["phase"] == "playing":
            room["game"]["log"] = f"Resposta incorreta. {player['name']} pagou M$ 50 ao banco."
        room["game"]["challenge"] = None
    broadcast_room(room)


@socketio.on("monopoly_buy")
def monopoly_buy():
    room, player = player_for_sid(request.sid)
    if not room or not room["started"]:
        emit_error("Entre em uma partida antes de comprar.")
        return
    game = room["game"]
    index = game["pending_buy"]
    if game["phase"] != "playing" or player["bankrupt"] or game["current"] != player["id"] or not game["has_rolled"] or index is None:
        emit_error("Não há uma propriedade disponível para comprar nesta jogada.")
        return
    space = game["board"][index]
    if space["owner"] is not None or player["money"] < space["price"]:
        emit_error("Propriedade indisponível ou dinheiro insuficiente.")
        return
    player["money"] -= space["price"]
    player["properties"].append(index)
    space["owner"] = player["id"]
    game["pending_buy"] = None
    game["log"] = f"{player['name']} comprou {space['name']} por M$ {space['price']}."
    broadcast_room(room)


@socketio.on("monopoly_pass")
def monopoly_pass():
    room, player = player_for_sid(request.sid)
    if not room or not room["started"]:
        emit_error("Entre em uma partida antes de decidir.")
        return
    game = room["game"]
    if (
        game["phase"] != "playing"
        or game["current"] != player["id"]
        or game["pending_buy"] is None
    ):
        emit_error("Não há uma propriedade aguardando sua decisão.")
        return
    space = game["board"][game["pending_buy"]]
    game["log"] = f"{player['name']} decidiu não comprar {space['name']}."
    game["pending_buy"] = None
    broadcast_room(room)


@socketio.on("monopoly_build")
def monopoly_build(data):
    room, player = player_for_sid(request.sid)
    if not room or not room["started"]:
        emit_error("Entre em uma partida antes de construir.")
        return
    game = room["game"]
    if game["current"] != player["id"] or game["phase"] != "playing" or player["bankrupt"]:
        emit_error("Só o jogador da vez pode construir.")
        return
    index = data.get("index") if isinstance(data, dict) else None
    if not isinstance(index, int) or not 0 <= index < len(game["board"]):
        emit_error("Propriedade inválida.")
        return
    space = game["board"][index]
    if space["type"] != "property" or space["owner"] != player["id"]:
        emit_error("Você não é dono desta rua.")
        return
    group = [
        item for item in game["board"]
        if item["type"] == "property" and item["color"] == space["color"]
    ]
    if not all(item["owner"] == player["id"] for item in group):
        emit_error("É preciso possuir todo o grupo de cor antes de construir.")
        return
    levels = [5 if item["hotel"] else item["houses"] for item in group]
    if (5 if space["hotel"] else space["houses"]) != min(levels):
        emit_error("Construa de forma equilibrada entre as ruas do grupo.")
        return
    if space["hotel"] or player["money"] < space["house_price"]:
        emit_error("Construção indisponível ou dinheiro insuficiente.")
        return
    player["money"] -= space["house_price"]
    if space["houses"] == 4:
        space["houses"] = 0
        space["hotel"] = True
        building = "um complexo"
    else:
        space["houses"] += 1
        building = "uma casa"
    game["log"] = f"{player['name']} construiu {building} em {space['name']} por M$ {space['house_price']}."
    broadcast_room(room)


@socketio.on("monopoly_end_turn")
def monopoly_end_turn():
    room, player = player_for_sid(request.sid)
    if not room or not room["started"]:
        emit_error("Entre em uma partida antes de encerrar a vez.")
        return
    game = room["game"]
    if (
        game["phase"] != "playing"
        or game["current"] != player["id"]
        or not game["has_rolled"]
        or game["challenge"]
        or game["pending_landing"]
        or game["pending_buy"] is not None
    ):
        emit_error("Não é possível encerrar a vez agora.")
        return
    game["log"] = f"{player['name']} encerrou a vez."
    next_turn(room)
    broadcast_room(room)


@socketio.on("leave_room")
def leave_game_room():
    room, player = player_for_sid(request.sid)
    if not room or not player:
        return
    leave_room(room["code"])
    if room["started"]:
        player["connected"] = False
        player["sid"] = None
        if room["game"]["current"] == player["id"]:
            next_turn(room)
    else:
        remove_lobby_player(room, player)
        if not room["players"]:
            rooms.pop(room["code"])
            return
    broadcast_room(room)


@socketio.on("disconnect")
def disconnect_player():
    room, player = player_for_sid(request.sid)
    if not room or not player:
        return
    if room["started"]:
        player["connected"] = False
        player["sid"] = None
        if room["game"]["current"] == player["id"]:
            next_turn(room)
    else:
        player["connected"] = False
        player["sid"] = None
        if room["host"] == player["id"]:
            connected = [
                player_id for player_id, other in room["players"].items()
                if other["connected"] and player_id != player["id"]
            ]
            if connected:
                room["host"] = connected[0]
    broadcast_room(room)


PAGE = r"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Monopoli de Mesa</title>
  <style>
    :root {
      color-scheme: dark;
      --ink: #f5f4eb;
      --muted: #a8b6ad;
      --felt: #123b31;
      --felt-dark: #0a2922;
      --gold: #f5c451;
      --tile: #f2efdb;
      --tile-ink: #15221d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(ellipse at 50% 30%, #1b4b3e, #081c18 78%);
      color: var(--ink);
      font: 17px/1.5 Inter, "Segoe UI", sans-serif;
    }
    button, input { font: inherit; }
    button {
      border: 0;
      border-radius: 10px;
      padding: 10px 15px;
      background: var(--gold);
      color: #18221c;
      font-weight: 800;
      cursor: pointer;
      transition: transform .15s, filter .15s;
    }
    button:hover:not(:disabled) { transform: translateY(-1px); filter: brightness(1.08); }
    button:disabled { cursor: not-allowed; opacity: .42; }
    button.secondary { background: #294c41; color: var(--ink); border: 1px solid #527163; }
    button.small { padding: 6px 9px; font-size: 13px; border-radius: 7px; }
    header {
      max-width: 1260px;
      margin: auto;
      padding: 18px 22px 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .brand { font-weight: 950; letter-spacing: .16em; font-size: 20px; }
    .brand span { color: var(--gold); }
    .subtitle { color: var(--muted); font-size: 14px; }
    main { max-width: 1260px; margin: auto; padding: 8px 18px 36px; }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 0 auto 12px;
      max-width: 1000px;
    }
    #status { color: #d8e8d8; min-height: 22px; font-weight: 650; }
    .board-scroll { overflow-x: auto; padding: 4px 0 12px; }
    .board {
      width: min(96vw, 1000px);
      min-width: 700px;
      aspect-ratio: 1;
      margin: auto;
      display: grid;
      grid-template: repeat(11, minmax(0, 1fr)) / repeat(11, minmax(0, 1fr));
      gap: 4px;
      padding: 7px;
      border-radius: 13px;
      background: #b9934b;
      box-shadow: 0 22px 70px #0008, inset 0 0 0 2px #f5da8c;
      position: relative;
    }
    .space {
      min-width: 0;
      overflow: hidden;
      position: relative;
      background: var(--tile);
      color: var(--tile-ink);
      border: 1px solid #293c30;
      border-radius: 3px;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      justify-content: flex-start;
      padding: 3px 2px;
      font-size: clamp(9px, .9vw, 13px);
      line-height: 1.18;
    }
    .space.edge-bottom { flex-direction: column-reverse; }
    .space.edge-left { flex-direction: row; }
    .space.edge-right { flex-direction: row-reverse; }
    .space.edge-left .band, .space.edge-right .band {
      width: 18%;
      height: 100%;
      flex: 0 0 18%;
    }
    .space.edge-left .space-copy, .space.edge-right .space-copy {
      writing-mode: vertical-rl;
      text-orientation: upright;
      max-height: 92%;
      max-width: 82%;
      overflow: hidden;
      font-size: clamp(9px, .85vw, 12px);
      font-weight: 850;
      line-height: 1.2;
    }
    .band { width: 100%; height: 17%; min-height: 4px; margin-bottom: 3px; }
    .space.edge-bottom .band { margin: 3px 0 0; }
    .space-corner { font-size: clamp(10px, 1vw, 14px); justify-content: center; }
    .space-corner .band { display: none; }
    .space-name { display: block; font-weight: 900; text-transform: uppercase; overflow-wrap: anywhere; }
    .space-price { margin-top: 3px; opacity: .8; font-size: .95em; }
    .space-owner { width: 7px; height: 7px; border-radius: 50%; margin-top: 2px; border: 1px solid #14241c; }
    .space-buildings { color: #147345; font-weight: 900; }
    .tokens { position: absolute; bottom: 2px; left: 1px; right: 1px; display: flex; justify-content: center; flex-wrap: wrap; gap: 1px; }
    .space.edge-bottom .tokens { top: 2px; bottom: auto; }
    .space.edge-left .tokens { left: 2px; right: auto; top: 2px; bottom: auto; flex-direction: column; }
    .space.edge-right .tokens { right: 2px; left: auto; top: 2px; bottom: auto; flex-direction: column; }
    .token {
      position: relative;
      width: 15px;
      height: 23px;
      flex: 0 0 15px;
      border: 0;
      border-radius: 0;
      background: none;
      filter: drop-shadow(2px 3px 1px #0008);
    }
    .pawn-animation-layer { position: absolute; inset: 0; z-index: 5; pointer-events: none; }
    .animated-pawn {
      position: absolute;
      z-index: 5;
      flex: none;
      margin: 0;
      transition: left .18s ease-in-out, top .18s ease-in-out;
      will-change: left, top;
    }
    @media (prefers-reduced-motion: reduce) {
      .animated-pawn { transition: none; }
    }
    .center-table {
      grid-row: 2 / span 9;
      grid-column: 2 / span 9;
      min-width: 0;
      min-height: 0;
      position: relative;
      border: 2px solid #aac0a354;
      border-radius: 8px;
      background:
        radial-gradient(circle at 50% 50%, #24624f, transparent 47%),
        linear-gradient(145deg, #174537, #0e3329);
      display: grid;
      grid-template: 1fr auto 1fr / 1fr 1fr 1fr;
      gap: 6px;
      padding: 10px;
    }
    .player-card {
      min-width: 0;
      max-height: 100%;
      overflow: hidden;
      border: 1px solid #d7c87860;
      border-top: 4px solid var(--player-color, #f5c451);
      border-radius: 10px;
      padding: 7px 9px;
      background: #09271fdb;
      box-shadow: 0 4px 12px #06140f55;
    }
    .player-card.active { border-color: var(--player-color); box-shadow: 0 0 0 2px var(--player-color), 0 6px 18px #0005; }
    .player-card.hidden { visibility: hidden; }
    .player-head { display: flex; align-items: center; gap: 7px; min-width: 0; }
    .player-token { width: 13px; height: 13px; flex: 0 0 13px; border-radius: 50%; border: 2px solid white; }
    .player-token.pawn {
      position: relative;
      width: 15px;
      height: 23px;
      flex: 0 0 15px;
      border: 0;
      border-radius: 0;
      filter: drop-shadow(2px 3px 1px #0008);
    }
    .pawn-head, .pawn-body, .pawn-base { position: absolute; display: block; }
    .pawn-head {
      z-index: 3;
      top: 0;
      left: 4px;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 25%, #fff, var(--pawn-color) 43%, #17251f);
      box-shadow: inset -2px -2px 3px #0006, inset 1px 1px 2px #fff8;
    }
    .pawn-body {
      z-index: 2;
      top: 6px;
      left: 4px;
      width: 8px;
      height: 11px;
      border-radius: 48% 48% 35% 35%;
      background: linear-gradient(110deg, #fff9, var(--pawn-color) 38%, #18241e);
      box-shadow: inset -2px -1px 3px #0007, inset 1px 0 2px #fff7;
    }
    .pawn-base {
      z-index: 1;
      bottom: 0;
      left: 0;
      width: 15px;
      height: 7px;
      border: 1px solid #ffffff99;
      border-radius: 50%;
      background: linear-gradient(150deg, #fff9, var(--pawn-color) 40%, #17251f);
      box-shadow: inset -2px -2px 3px #0008, inset 1px 1px 2px #fff8, 0 2px 0 #0007;
    }
    .player-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 900; font-size: clamp(13px, 1.2vw, 17px); }
    .player-turn { margin-left: auto; color: var(--gold); font-size: 12px; font-weight: 900; }
    .player-money { font-size: clamp(20px, 2vw, 28px); font-weight: 950; letter-spacing: -.04em; margin: 3px 0; color: #f6d273; }
    .property-title { color: var(--muted); text-transform: uppercase; letter-spacing: .12em; font-size: 11px; font-weight: 850; }
    .owned-list { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; max-height: 53px; overflow-y: auto; }
    .owned-property { border-left: 3px solid var(--prop-color, #9aa79c); border-radius: 4px; padding: 4px 6px; background: #ffffff12; font-size: 12px; line-height: 1.3; }
    .owned-property button { display: block; margin-top: 3px; }
    .no-properties { color: #a2b0a7; font-size: 13px; font-style: italic; }
    .slot-0 { grid-row: 1; grid-column: 1; }
    .slot-1 { grid-row: 1; grid-column: 3; }
    .slot-2 { grid-row: 3; grid-column: 3; }
    .slot-3 { grid-row: 3; grid-column: 1; }
    .dice-area {
      grid-row: 2;
      grid-column: 2;
      align-self: center;
      justify-self: center;
      width: min(100%, 230px);
      padding: 14px 10px;
      border-radius: 50%;
      text-align: center;
      background: #09271fbf;
      border: 1px solid #f5c45155;
    }
    .table-title { font-size: 13px; color: #c5d5ca; letter-spacing: .13em; text-transform: uppercase; font-weight: 900; }
    .dice-cubes { display: flex; justify-content: center; gap: 9px; margin: 6px 0; }
    .die {
      width: 54px;
      height: 54px;
      display: grid;
      place-items: center;
      border: 1px solid #fff;
      border-radius: 12px;
      background: linear-gradient(145deg, #fffdf4, #d9d2b8);
      color: #18362b;
      font-size: 42px;
      font-weight: 950;
      line-height: 1;
      text-shadow: 0 1px 1px #fff;
      box-shadow: 0 6px 0 #a69872, 0 8px 10px #0006, inset 3px 3px 6px #fff;
      transform: perspective(140px) rotateX(9deg) rotateY(-9deg);
    }
    .dice-cubes.rolling .die { animation: bounce .2s ease-in-out infinite alternate; }
    @keyframes bounce {
      to { transform: perspective(140px) translateY(-6px) rotateX(28deg) rotateY(18deg) rotateZ(8deg); }
    }
    .turn-label { color: var(--gold); font-size: 14px; font-weight: 850; min-height: 20px; }
    .center-controls { display: flex; justify-content: center; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
    .center-controls button { padding: 9px 12px; font-size: 13px; }
    .log {
      max-width: 1000px;
      min-height: 38px;
      margin: 2px auto 0;
      padding: 9px 12px;
      border: 1px solid #ffffff20;
      border-radius: 9px;
      color: #d4e0d6;
      background: #061a157d;
      font-size: 15px;
    }
    .instructions { color: var(--muted); max-width: 1000px; margin: 9px auto; font-size: 14px; }
    .overlay {
      position: fixed;
      inset: 0;
      z-index: 20;
      padding: 18px;
      display: grid;
      place-items: center;
      background: #03100ed9;
      backdrop-filter: blur(8px);
    }
    .overlay.hidden { display: none; }
    .dialog {
      width: min(520px, 100%);
      max-height: 90vh;
      overflow-y: auto;
      padding: 25px;
      border: 1px solid #e4c66d66;
      border-radius: 18px;
      background: #102d25;
      box-shadow: 0 20px 80px #000a;
    }
    .dialog h1, .dialog h2 { margin: 0 0 8px; }
    .dialog p { color: #bfcec2; }
    .name-input { width: 100%; margin: 5px 0; padding: 11px; color: var(--ink); border: 1px solid #52695b; border-radius: 8px; background: #091e18; }
    .choice { width: 100%; margin: 5px 0; text-align: left; background: #294c41; color: var(--ink); border: 1px solid #587261; }
    .dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 15px; }
    .card-badge { color: #111f17; background: var(--gold); padding: 5px 10px; border-radius: 20px; display: inline-block; font-size: 12px; font-weight: 950; letter-spacing: .12em; }
    .rule-note { color: #aabdaf; font-size: 14px; margin-top: 12px; }
    .hidden { display: none !important; }
    .lobby-card { max-width: 620px; margin: 28px auto; padding: 26px; border: 1px solid #e4c66d66; border-radius: 18px; background: #102d25; box-shadow: 0 18px 60px #0006; }
    .lobby-card h1, .lobby-card h2 { margin-top: 4px; }
    .lobby-card p { color: #bfcec2; }
    .lobby-input { width: 100%; margin: 6px 0; padding: 12px; color: var(--ink); border: 1px solid #52695b; border-radius: 8px; background: #091e18; }
    .lobby-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .lobby-divider { border: 0; border-top: 1px solid #ffffff1c; margin: 22px 0; }
    .room-code { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 16px 0; padding: 14px; border: 1px solid #f5c45166; border-radius: 12px; background: #09271f; }
    .room-code strong { color: var(--gold); letter-spacing: .2em; font-size: 28px; }
    .lobby-player { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin: 7px 0; padding: 11px; border-radius: 9px; background: #ffffff0b; }
    .lobby-player-name { display: flex; align-items: center; gap: 8px; font-weight: 800; }
    .connection-pill { color: #9dc6a9; font-size: 14px; }
    #connection-status { color: #c4d2c7; font-size: 14px; }
    #feedback, #feedback-lobby { min-height: 22px; margin-top: 9px; color: #ffd274; font-size: 15px; }
    .room-copy { color: var(--muted); font-size: 15px; }
    #lobby-start-note { color: var(--muted); font-size: 15px; }
    .chat-panel {
      position: fixed;
      z-index: 25;
      right: 16px;
      bottom: 16px;
      width: min(340px, calc(100vw - 24px));
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid #e4c66d88;
      border-radius: 13px;
      background: #0b241ef5;
      box-shadow: 0 10px 35px #0009;
    }
    .chat-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 12px; border-bottom: 1px solid #ffffff24; }
    .chat-title { font-weight: 900; letter-spacing: .08em; }
    .chat-room { overflow: hidden; color: var(--muted); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
    .chat-messages { height: 154px; overflow-y: auto; padding: 8px 11px; display: flex; flex-direction: column; gap: 7px; }
    body:not(.chat-active) .chat-messages { height: 64px; }
    .chat-empty { margin: auto; color: var(--muted); font-size: 14px; text-align: center; }
    .chat-message { overflow-wrap: anywhere; color: #e8eee9; font-size: 14px; line-height: 1.35; }
    .chat-message-meta { display: flex; align-items: baseline; gap: 7px; margin-bottom: 1px; }
    .chat-author { font-weight: 850; }
    .chat-time { color: var(--muted); font-size: 11px; }
    .chat-form { display: flex; gap: 7px; padding: 8px; border-top: 1px solid #ffffff24; }
    .chat-input { min-width: 0; flex: 1; padding: 9px; border: 1px solid #52695b; border-radius: 8px; background: #091e18; color: var(--ink); }
    .chat-form button { flex: 0 0 auto; padding: 8px 12px; }
    .chat-panel[aria-disabled="true"] .chat-input { opacity: .7; }
    @media (max-width: 720px) {
      header { padding-inline: 14px; }
      main { padding-inline: 8px; }
      .board { width: 700px; }
      .topbar { padding: 0 5px; }
      .subtitle { display: none; }
      .player-card { padding: 5px; }
      .chat-panel { right: 10px; bottom: 10px; width: min(350px, calc(100vw - 20px)); }
      .chat-messages { height: 112px; }
      body:not(.chat-active) .chat-messages { height: 44px; }
    }
  </style>
</head>
<body>
  <header>
    <div><div class="brand">MONOPOLI <span>ONLINE</span></div><div class="subtitle">Uma sala privada para até quatro jogadores</div></div>
    <div style="display:flex;align-items:center;gap:12px">
      <span id="connection-status" aria-live="polite">Conectando...</span>
      <button class="secondary small hidden" id="leave-room" type="button">Sair da sala</button>
    </div>
  </header>
  <main>
    <section class="lobby-card" id="home-screen">
      <span class="card-badge">MULTIPLAYER · TEMPO REAL</span>
      <h1>Entre na mesa</h1>
      <p>Crie uma sala de espera e compartilhe o código com seus amigos, ou entre em uma sala existente.</p>
      <label for="player-name">Seu nome</label>
      <input class="lobby-input" id="player-name" maxlength="18" placeholder="Ex.: Ana" autocomplete="nickname">
      <div class="lobby-actions"><button id="create-room" type="button">Criar sala</button></div>
      <hr class="lobby-divider">
      <label for="join-code">Código da sala</label>
      <input class="lobby-input" id="join-code" maxlength="5" placeholder="ABC12" autocomplete="off">
      <div class="lobby-actions"><button class="secondary" id="join-room" type="button">Entrar na sala</button></div>
      <div id="feedback" aria-live="polite"></div>
    </section>
    <section class="lobby-card hidden" id="waiting-screen">
      <span class="card-badge">SALA DE ESPERA</span>
      <h1>Convide seus amigos</h1>
      <div class="room-code"><div><div class="room-copy">CÓDIGO DA SALA</div><strong id="room-code"></strong></div><button class="secondary small" id="copy-code" type="button">Copiar código</button></div>
      <p id="lobby-start-note">Aguardando jogadores entrarem na sala.</p>
      <h2>Jogadores <span class="room-copy" id="player-count"></span></h2>
      <div id="lobby-players"></div>
      <div class="lobby-actions">
        <button id="start-game" type="button" class="hidden">Iniciar partida</button>
        <button id="leave-lobby" type="button" class="secondary">Sair da sala</button>
      </div>
      <div id="feedback-lobby" aria-live="polite"></div>
    </section>
    <section class="hidden" id="game-screen">
      <div class="topbar">
        <div id="status" aria-live="polite">Aguardando estado da partida...</div>
        <div><button class="secondary small" id="rules-button" type="button">Como jogar</button></div>
      </div>
      <div class="board-scroll">
        <section class="board" id="board" aria-label="Tabuleiro de jogo"></section>
      </div>
      <div class="log" id="log" aria-live="polite">Aguardando os jogadores.</div>
      <p class="instructions">Passe pela Partida para receber M$ 200. Complete grupos de cor para construir casas e, com quatro casas, evolua para um complexo. Parar no estacionamento livre não dá bônus.</p>
    </section>
  </main>

  <aside class="chat-panel" id="chat-panel" aria-label="Chat da sala" aria-disabled="true">
    <div class="chat-header">
      <span class="chat-title">CHAT</span>
      <span class="chat-room" id="chat-room-label">Entre em uma sala para conversar</span>
    </div>
    <div class="chat-messages" id="chat-messages" role="log" aria-live="polite">
      <div class="chat-empty">As mensagens da sala aparecerão aqui.</div>
    </div>
    <form class="chat-form" id="chat-form">
      <input class="chat-input" id="chat-input" maxlength="500" placeholder="Escreva uma mensagem..." aria-label="Escreva uma mensagem" disabled>
      <button type="submit" id="chat-send" disabled>Enviar</button>
    </form>
  </aside>

  <div class="overlay hidden" id="challenge">
    <section class="dialog" role="dialog" aria-modal="true" aria-labelledby="challenge-title">
      <span class="card-badge" id="challenge-kind">CARTA DE DESAFIO</span>
      <h2 id="challenge-title"></h2>
      <div id="challenge-options"></div>
      <p id="challenge-waiting" class="rule-note hidden">Aguardando a resposta de quem tirou a carta...</p>
      <p id="challenge-note" class="rule-note">Pergunta criada a partir das regras resumidas no arquivo 00009_pt-br_monopoly.txt.</p>
    </section>
  </div>
  <div class="overlay hidden" id="property-decision">
    <section class="dialog" role="dialog" aria-modal="true" aria-labelledby="property-decision-title">
      <span class="card-badge" id="property-decision-badge">DECISÃO DA JOGADA</span>
      <h2 id="property-decision-title"></h2>
      <p id="property-decision-detail"></p>
      <div id="property-decision-actions"></div>
      <p id="property-decision-waiting" class="rule-note hidden">Aguardando a decisão do jogador da vez...</p>
    </section>
  </div>
  <div class="overlay hidden" id="rules">
    <section class="dialog">
      <span class="card-badge">REGRAS RÁPIDAS</span>
      <h2>Como jogar</h2>
      <p>Na sua vez, role os dados e avance. Ao cair em uma propriedade livre, compre-a; se já tiver dono, pague aluguel. Impostos são pagos ao banco e as casas de Sorte e Comunidade trazem perguntas sobre as regras.</p>
      <p>Quando tiver todas as propriedades da mesma cor, pode construir uma casa por vez em cada rua do grupo, mantendo a construção equilibrada. Com quatro casas em uma rua, transforme-as em um complexo.</p>
      <p>Se não conseguir pagar uma dívida, você sai da partida e suas propriedades voltam ao banco. Vence o último jogador que permanecer.</p>
      <p class="rule-note">Versão de mesa simplificada: não inclui negociações nem leilões automáticos.</p>
      <div class="dialog-actions"><button id="close-rules" type="button">Entendi</button></div>
    </section>
  </div>
  <div class="overlay hidden" id="game-over">
    <section class="dialog">
      <span class="card-badge">FIM DE JOGO</span>
      <h2 id="winner-title"></h2>
      <p id="winner-copy"></p>
      <div class="dialog-actions"><button id="game-over-close" type="button">Fechar</button></div>
    </section>
  </div>

  <script src="https://cdn.socket.io/4.8.1/socket.io.min.js"></script>
  <script>
    const initialBoard = {{ board|tojson }};
    const colors = ["#f05a61", "#53b8f3", "#e9b949", "#bb83ea"];
    const colorBands = {
      brown: "#8e5d3c", lightblue: "#86d8e9", pink: "#db83bd",
      orange: "#f09a42", red: "#ed5553", yellow: "#f2d94f",
      green: "#52a876", darkblue: "#4f6bd8"
    };
    const challenges = [
      {q:"Ao completar um grupo de cor, qual construção fica disponível?", a:["Casas","Somente estações","Nenhuma construção"], correct:0, reward:100},
      {q:"Qual é o valor recebido ao passar pela Partida?", a:["M$ 100","M$ 200","M$ 500"], correct:1, reward:100},
      {q:"Quantas casas cabem em uma rua antes da evolução para complexo?", a:["Duas","Quatro","Seis"], correct:1, reward:100},
      {q:"O que acontece com o aluguel de uma propriedade hipotecada?", a:["Não é cobrado enquanto estiver hipotecada","É sempre dobrado","Vai para o centro do tabuleiro"], correct:0, reward:100},
      {q:"Quantos lançamentos duplos seguidos mandam um jogador para a prisão?", a:["Dois","Três","Quatro"], correct:1, reward:100},
      {q:"O que é necessário para construir casas em uma rua?", a:["Ter o grupo de cor completo","Ter passado duas vezes pela Partida","Possuir uma estação"], correct:0, reward:100},
      {q:"Parar no estacionamento livre rende um prêmio em dinheiro?", a:["Sim, M$ 200","Sim, o valor dos impostos","Não, é apenas uma parada livre"], correct:2, reward:100},
      {q:"Ao cair em uma propriedade sem dono, o jogador pode comprá-la?", a:["Sim, pagando o preço indicado","Só depois de uma volta completa","Não, apenas o banqueiro pode"], correct:0, reward:100},
      {q:"Se a dívida não puder ser paga, qual é o resultado previsto nas regras?", a:["O jogador continua sem pagar","O jogador sai da partida","Todos dividem a dívida"], correct:1, reward:100},
      {q:"Como os hotéis/complexos são construídos nesta versão das regras?", a:["Depois de quatro casas na rua","Antes da primeira casa","Somente em estações"], correct:0, reward:100},
      {q:"Qual é o valor inicial por jogador indicado no arquivo de regras?", a:["M$ 1.000","M$ 1.500","M$ 2.000"], correct:1, reward:100},
      {q:"Quando alguém recusa comprar uma propriedade livre, a regra tradicional prevê o quê?", a:["Leilão entre jogadores","Propriedade removida","Aluguel imediato"], correct:0, reward:100}
    ];
    const corners = {0:[11,11], 10:[11,1], 20:[1,1], 30:[1,11]};
    let state = null;
    let currentChallenge = null;

    const $ = (id) => document.getElementById(id);
    const money = (value) => "M$ " + Math.max(0, value).toLocaleString("pt-BR");
    const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    })[char]);

    function spaceGridPosition(index) {
      if (corners[index]) return corners[index];
      if (index < 10) return [11, 11 - index];
      if (index < 20) return [21 - index, 1];
      if (index < 30) return [1, index - 19];
      return [index - 29, 11];
    }

    function buildBoard() {
      const board = $("board");
      board.replaceChildren();
      initialBoard.forEach((space, index) => {
        const [row, column] = spaceGridPosition(index);
        const tile = document.createElement("div");
        const edge = row === 11 ? "edge-bottom" : column === 1 ? "edge-left" : column === 11 ? "edge-right" : "edge-top";
        tile.className = "space " + edge + (corners[index] ? " space-corner" : "");
        tile.dataset.index = index;
        tile.style.gridRow = row;
        tile.style.gridColumn = column;
        const band = space.color ? `<div class="band" style="background:${colorBands[space.color]}"></div>` : "";
        const price = space.price ? `<div class="space-price">M$ ${space.price}</div>` : "";
        tile.innerHTML = `${band}<div class="space-copy"><span class="space-name">${escapeHtml(space.name)}</span>${price}<div class="space-buildings"></div></div><div class="tokens"></div>`;
        board.appendChild(tile);
      });
      const center = document.createElement("div");
      center.className = "center-table";
      center.innerHTML = `<div class="player-card slot-0" data-slot="0"></div>
        <div class="player-card slot-1" data-slot="1"></div>
        <div class="player-card slot-2" data-slot="2"></div>
        <div class="player-card slot-3" data-slot="3"></div>
        <div class="dice-area">
          <div class="table-title">Mesa de jogo</div>
          <div class="dice-cubes" id="dice"><span class="die" id="die-one">⚀</span><span class="die" id="die-two">⚀</span></div>
          <div class="turn-label" id="turn-label">Adicione os jogadores</div>
          <div class="center-controls">
            <button id="roll-button" type="button" disabled>Rolar dados</button>
            <button id="end-button" class="secondary" type="button" disabled>Encerrar vez</button>
          </div>
        </div>`;
      board.appendChild(center);
      const animationLayer = document.createElement("div");
      animationLayer.className = "pawn-animation-layer";
      animationLayer.id = "pawn-animation-layer";
      board.appendChild(animationLayer);
      $("roll-button").addEventListener("click", rollDice);
      $("end-button").addEventListener("click", endTurn);
      render();
    }

    function showNameInputs() {
      const count = Number($("player-count").value);
      const fields = $("name-fields");
      fields.replaceChildren();
      for (let i = 0; i < count; i += 1) {
        const input = document.createElement("input");
        input.className = "name-input";
        input.id = `player-name-${i}`;
        input.maxLength = 18;
        input.placeholder = `Nome do jogador ${i + 1}`;
        input.setAttribute("aria-label", `Nome do jogador ${i + 1}`);
        input.value = `Jogador ${i + 1}`;
        fields.appendChild(input);
      }
    }

    function beginGame() {
      const count = Number($("player-count").value);
      const players = [];
      for (let i = 0; i < count; i += 1) {
        const name = $(`player-name-${i}`).value.trim();
        if (!name) {
          $(`player-name-${i}`).focus();
          $("status").textContent = "Preencha o nome de todos os jogadores.";
          return;
        }
        players.push({name, money:1500, pos:0, properties:[], color:colors[i], jailed:false, bankrupt:false});
      }
      state = {
        board: initialBoard.map((space) => ({...space})),
        players, current:0, hasRolled:false, pendingBuy:null,
        dice:[1,1], log:"Partida iniciada! Boa sorte."
      };
      $("setup").classList.add("hidden");
      render();
    }

    function currentPlayer() { return state && state.players[state.current]; }
    function updateLog(text) { state.log = text; $("log").textContent = text; }

    function pay(player, amount, recipient) {
      if (player.money < amount) {
        player.money = 0;
        player.bankrupt = true;
        player.properties.forEach((index) => {
          const space = state.board[index];
          space.owner = null;
          space.houses = 0;
          space.hotel = false;
        });
        player.properties = [];
        updateLog(`${player.name} não conseguiu pagar M$ ${amount} e saiu da partida. As propriedades voltaram ao banco.`);
        if (!checkWinner()) {
          advanceTurn();
          updateLog(`${player.name} faliu. É a vez de ${currentPlayer().name}.`);
        }
        return false;
      }
      player.money -= amount;
      if (recipient) recipient.money += amount;
      return true;
    }

    function checkWinner() {
      const active = state.players.filter((player) => !player.bankrupt);
      if (active.length > 1) return false;
      $("roll-button").disabled = true;
      $("end-button").disabled = true;
      if (active.length === 1) {
        $("winner-title").textContent = `${active[0].name} venceu!`;
        $("winner-copy").textContent = `A partida terminou com ${money(active[0].money)}.`;
      } else {
        $("winner-title").textContent = "Partida encerrada";
        $("winner-copy").textContent = "Todos os jogadores faliram.";
      }
      $("game-over").classList.remove("hidden");
      return true;
    }

    function rollDice() {
      socket.emit("monopoly_roll");
    }

    function landOnSpace(player, space, diceTotal) {
      if (space.type === "property" || space.type === "railroad" || space.type === "utility") {
        if (!space.owner) {
          state.pendingBuy = state.board.indexOf(space);
          updateLog(`${player.name} chegou a ${space.name}, disponível por M$ ${space.price}.`);
          return;
        }
        if (space.owner === state.current) return;
        const owner = state.players[space.owner];
        if (!owner || owner.bankrupt) return;
        let rent = space.rent || 0;
        if (space.type === "railroad") {
          const railroads = owner.properties.map((i) => state.board[i]).filter((item) => item.type === "railroad").length;
          rent = 25 * (2 ** Math.max(0, railroads - 1));
        } else if (space.type === "utility") {
          const utilities = owner.properties.map((i) => state.board[i]).filter((item) => item.type === "utility").length;
          rent = diceTotal * (utilities === 2 ? 10 : 4);
        } else {
          const group = state.board.filter((item) => item.type === "property" && item.color === space.color);
          const ownsGroup = group.every((item) => item.owner === space.owner);
          if (space.hotel) rent = space.rent * 12;
          else if (space.houses) rent = space.rent * (space.houses + 1) * 2;
          else if (ownsGroup) rent *= 2;
        }
        if (pay(player, rent, owner)) updateLog(`${player.name} pagou M$ ${rent} de aluguel para ${owner.name}.`);
        return;
      }
      if (space.type === "tax") {
        if (pay(player, space.amount)) updateLog(`${player.name} pagou M$ ${space.amount} de imposto.`);
        return;
      }
      if (space.type === "chance" || space.type === "community") {
        drawChallenge(space.type);
        return;
      }
      if (space.type === "go_to_jail") {
        player.pos = 10;
        player.jailed = true;
        updateLog(`${player.name} foi enviado à prisão e perderá a próxima vez, ou poderá pagar M$ 50 para sair.`);
        return;
      }
      if (space.type === "go") updateLog(`${player.name} recebeu M$ 200 na Partida.`);
      if (space.type === "free") updateLog(`${player.name} parou no estacionamento livre. Sem bônus.`);
      if (space.type === "jail") updateLog(`${player.name} está apenas de visita à prisão.`);
    }

    function drawChallenge(kind) {
      currentChallenge = challenges[Math.floor(Math.random() * challenges.length)];
      $("challenge-kind").textContent = kind === "chance" ? "SORTE · DESAFIO" : "COMUNIDADE · DESAFIO";
      $("challenge-title").textContent = currentChallenge.q;
      const choices = $("challenge-options");
      choices.replaceChildren();
      currentChallenge.a.forEach((answer, index) => {
        const button = document.createElement("button");
        button.className = "choice";
        button.textContent = answer;
        button.addEventListener("click", () => answerChallenge(index));
        choices.appendChild(button);
      });
      $("challenge").classList.remove("hidden");
    }

    function answerChallenge(choice) {
      socket.emit("monopoly_challenge_answer", {answer: choice});
    }

    function buyProperty() {
      socket.emit("monopoly_buy");
    }

    function buildOn(index) {
      socket.emit("monopoly_build", {index});
    }

    function advanceTurn() {
      state.hasRolled = false;
      state.pendingBuy = null;
      for (let step = 1; step <= state.players.length; step += 1) {
        const next = (state.current + step) % state.players.length;
        if (!state.players[next].bankrupt) {
          state.current = next;
          break;
        }
      }
      const player = currentPlayer();
      updateLog(player.jailed
        ? `${player.name}, sua vez: pague M$ 50 para sair da prisão.`
        : `É a vez de ${player.name}.`);
      render();
    }

    function endTurn() {
      socket.emit("monopoly_end_turn");
    }

    function render() {
      if (!state) {
        document.querySelectorAll(".player-card").forEach((card) => card.classList.add("hidden"));
        return;
      }
      document.querySelectorAll(".player-card").forEach((card, slot) => {
        const player = state.players[slot];
        if (!player) {
          card.classList.add("hidden");
          card.replaceChildren();
          return;
        }
        card.classList.remove("hidden");
        card.style.setProperty("--player-color", player.color);
        card.classList.toggle("active", slot === state.current);
        const holdings = player.properties.map((index) => {
          const space = state.board[index];
          const level = space.hotel ? "Complexo" : space.houses ? `${space.houses} casa${space.houses > 1 ? "s" : ""}` : "Terreno";
          const build = slot === state.current && player.id === myPlayerId && socket.connected && !movingPawns.has(player.id) && !player.bankrupt && !state.pending_landing && state.pending_buy === null && !state.challenge && space.type === "property"
            ? `<button class="small secondary build-button" data-index="${index}" type="button">Construir · M$ ${space.house_price}</button>` : "";
          return `<div class="owned-property" style="--prop-color:${colorBands[space.color] || player.color}">${escapeHtml(space.name)} · ${level}${build}</div>`;
        }).join("");
        card.innerHTML = `        <div class="player-head"><span class="player-token pawn" style="--pawn-color:${player.color}"><i class="pawn-head"></i><i class="pawn-body"></i><i class="pawn-base"></i></span>
          <span class="player-name">${escapeHtml(player.name)}${player.bankrupt ? " · falido" : !player.connected ? " · offline" : ""}</span>
          ${slot === state.current && !player.bankrupt ? '<span class="player-turn">SUA VEZ</span>' : ""}</div>
          <div class="player-money">${money(player.money)}</div><div class="property-title">Propriedades</div>
          <div class="owned-list">${holdings || '<span class="no-properties">Ainda sem propriedades</span>'}</div>`;
      });
      state.board.forEach((space, index) => {
        const tile = document.querySelector(`.space[data-index="${index}"]`);
        if (!tile) return;
        const owner = space.owner === null ? "" : state.players[space.owner];
        const ownerMark = tile.querySelector(".space-owner");
        if (ownerMark) ownerMark.remove();
        if (owner) {
          const mark = document.createElement("span");
          mark.className = "space-owner";
          mark.style.background = owner.color;
          tile.querySelector(".space-copy").appendChild(mark);
        }
        const buildings = tile.querySelector(".space-buildings");
        if (buildings) buildings.textContent = space.hotel ? "◆" : space.houses ? "⌂".repeat(space.houses) : "";
        const tokens = tile.querySelector(".tokens");
        tokens.replaceChildren();
        state.players.forEach((player) => {
          if (!player.bankrupt && player.pos === index) {
            const token = document.createElement("span");
            token.className = "token";
            token.style.setProperty("--pawn-color", player.color);
            token.title = player.name;
            token.innerHTML = '<i class="pawn-head"></i><i class="pawn-body"></i><i class="pawn-base"></i>';
            tokens.appendChild(token);
          }
        });
      });
      const player = currentPlayer();
      $("turn-label").textContent = player ? (player.bankrupt ? "Fim de jogo" : `Vez: ${player.name}${player.jailed ? " · prisão" : ""}`) : "Adicione os jogadores";
      const dieFaces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];
      $("die-one").textContent = dieFaces[state.dice[0] - 1];
      $("die-two").textContent = dieFaces[state.dice[1] - 1];
      const isMyTurn = Boolean(player && player.id === myPlayerId && socket.connected && !movingPawns.has(player.id) && state.phase === "playing");
      $("roll-button").disabled = !isMyTurn || player.bankrupt || state.has_rolled || Boolean(state.challenge) || state.pending_landing !== null || state.pending_buy !== null;
      $("roll-button").textContent = player && player.jailed ? "Pagar M$ 50 e sair" : "Rolar dados";
      $("end-button").disabled = !isMyTurn || !state.has_rolled || player.bankrupt || Boolean(state.challenge) || state.pending_landing !== null || state.pending_buy !== null;
      $("log").textContent = state.log;
      document.querySelectorAll(".build-button").forEach((button) => {
        button.addEventListener("click", () => buildOn(Number(button.dataset.index)));
      });
      if (player && !player.bankrupt) $("status").textContent = `Jogada ${state.dice[0]} + ${state.dice[1]} · ${player.name} tem ${money(player.money)}.`;
    }

    $("rules-button").addEventListener("click", () => $("rules").classList.remove("hidden"));
    $("close-rules").addEventListener("click", () => $("rules").classList.add("hidden"));
    buildBoard();
  </script>
  <script>
    const socket = io();
    let myToken = sessionStorage.getItem("monopolyToken");
    let myPlayerId = sessionStorage.getItem("monopolyPlayerId");
    let activeRoomCode = sessionStorage.getItem("monopolyRoom");
    let latestRoom = null;
    const movingPawns = new Set();

    function pawnPosition(spaceIndex, playerIndex) {
      const tile = document.querySelector(`.space[data-index="${spaceIndex}"]`);
      const boardRect = $("board").getBoundingClientRect();
      const tileRect = tile.getBoundingClientRect();
      const stagger = (playerIndex - 1.5) * 4;
      let x = tileRect.left - boardRect.left + tileRect.width / 2 + stagger;
      let y = tileRect.top - boardRect.top + tileRect.height / 2;
      if (spaceIndex <= 10) y = tileRect.top - boardRect.top + 14;
      else if (spaceIndex <= 20) x = tileRect.left - boardRect.left + 14;
      else if (spaceIndex <= 30) y = tileRect.bottom - boardRect.top - 14;
      else x = tileRect.right - boardRect.left - 14;
      return [x, y];
    }

    function animatePawn(move) {
      const playerIndex = state.players.findIndex((player) => player.id === move.id);
      const player = state.players[playerIndex];
      if (!player || playerIndex < 0) return;
      const pawn = document.createElement("span");
      pawn.className = "token animated-pawn";
      pawn.style.setProperty("--pawn-color", player.color);
      pawn.innerHTML = '<i class="pawn-head"></i><i class="pawn-body"></i><i class="pawn-base"></i>';
      pawn.title = player.name;
      $("pawn-animation-layer").appendChild(pawn);
      const placeAt = (index) => {
        const [x, y] = pawnPosition(index, playerIndex);
        pawn.style.left = `${x}px`;
        pawn.style.top = `${y}px`;
        pawn.style.transform = "translate(-50%, -50%)";
      };
      const distance = (move.to - move.from + state.board.length) % state.board.length;
      const steps = move.jailed
        ? (move.landing - move.from + state.board.length) % state.board.length
        : distance;
      placeAt(move.from);
      let step = 0;
      const interval = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 195;
      const finish = () => {
        pawn.remove();
        movingPawns.delete(move.id);
        render();
      };
      const advance = () => {
        if (step >= steps) {
          if (move.jailed) {
            step += 1;
            placeAt(10);
            setTimeout(finish, interval);
          } else {
            finish();
          }
          return;
        }
        step += 1;
        placeAt((move.from + step) % state.board.length);
        setTimeout(advance, interval);
      };
      requestAnimationFrame(() => setTimeout(advance, interval));
    }

    function setScreen(screen) {
      $("home-screen").classList.toggle("hidden", screen !== "home");
      $("waiting-screen").classList.toggle("hidden", screen !== "waiting");
      $("game-screen").classList.toggle("hidden", screen !== "game");
      $("leave-room").classList.toggle("hidden", screen === "home");
    }

    function feedback(message, target = "feedback") {
      $(target).textContent = message;
    }

    function saveSession(code, token, playerId) {
      activeRoomCode = code;
      myToken = token;
      myPlayerId = playerId;
      sessionStorage.setItem("monopolyRoom", code);
      sessionStorage.setItem("monopolyToken", token);
      sessionStorage.setItem("monopolyPlayerId", playerId);
    }

    function clearSession() {
      activeRoomCode = null;
      myToken = null;
      myPlayerId = null;
      latestRoom = null;
      state = null;
      sessionStorage.removeItem("monopolyRoom");
      sessionStorage.removeItem("monopolyToken");
      sessionStorage.removeItem("monopolyPlayerId");
      $("challenge").classList.add("hidden");
      $("game-over").classList.add("hidden");
      $("chat-room-label").textContent = "Entre em uma sala para conversar";
      $("chat-messages").innerHTML = '<div class="chat-empty">As mensagens da sala aparecerão aqui.</div>';
      setChatAvailable(false);
      setScreen("home");
    }

    function setChatAvailable(available) {
      $("chat-input").disabled = !available;
      $("chat-send").disabled = !available;
      $("chat-panel").setAttribute("aria-disabled", String(!available));
      document.body.classList.toggle("chat-active", available);
    }

    function appendChatMessage(message) {
      const messages = $("chat-messages");
      const empty = messages.querySelector(".chat-empty");
      if (empty) empty.remove();
      const item = document.createElement("article");
      item.className = "chat-message";
      const meta = document.createElement("div");
      meta.className = "chat-message-meta";
      const author = document.createElement("span");
      author.className = "chat-author";
      author.style.color = message.color;
      author.textContent = message.name;
      const time = document.createElement("time");
      time.className = "chat-time";
      time.textContent = message.time;
      const text = document.createElement("div");
      text.textContent = message.message;
      meta.append(author, time);
      item.append(meta, text);
      messages.append(item);
      while (messages.children.length > 100) messages.firstElementChild.remove();
      messages.scrollTop = messages.scrollHeight;
    }

    function enterRoom(room) {
      latestRoom = room;
      $("chat-room-label").textContent = `Sala ${room.code}`;
      setChatAvailable(socket.connected);
      $("room-code").textContent = room.code;
      $("player-count").textContent = `(${room.players.length}/4)`;
      $("lobby-players").innerHTML = room.players.map((player) => {
        const tags = [
          player.id === room.host ? "anfitrião" : "",
          player.id === myPlayerId ? "você" : "",
          player.connected ? "online" : "reconectando",
        ].filter(Boolean).join(" · ");
        return `<div class="lobby-player">
          <span class="lobby-player-name"><span class="player-token" style="background:${player.color}"></span>${escapeHtml(player.name)}</span>
          <span class="connection-pill">${escapeHtml(tags)}</span>
        </div>`;
      }).join("");
      const host = room.host === myPlayerId;
      const startButton = $("start-game");
      startButton.classList.toggle("hidden", !host);
      startButton.disabled = room.players.filter((player) => player.connected).length < 2;
      $("lobby-start-note").textContent = host
        ? (startButton.disabled ? "Compartilhe o código e aguarde pelo menos mais um jogador." : "Todos prontos? Você pode iniciar a partida.")
        : "Aguardando o anfitrião iniciar a partida.";
      if (!room.started) setScreen("waiting");
    }

    function showChallenge(challenge) {
      if (!challenge) {
        $("challenge").classList.add("hidden");
        return;
      }
      $("property-decision").classList.add("hidden");
      $("challenge-kind").textContent = challenge.purpose === "rent"
        ? "DESAFIO · ALUGUEL"
        : challenge.kind === "chance" ? "SORTE · DESAFIO" : "COMUNIDADE · DESAFIO";
      const player = state.players.find((item) => item.id === challenge.player);
      $("challenge-title").textContent = `${player ? player.name : "Jogador"}: ${challenge.q}`;
      $("challenge-note").textContent = challenge.purpose === "rent"
        ? `Acerte para não pagar ${money(challenge.rent)} de aluguel. Se errar, o aluguel será cobrado.`
        : "Pergunta criada a partir das regras resumidas no arquivo 00009_pt-br_monopoly.txt.";
      const canAnswer = challenge.player === myPlayerId && socket.connected;
      $("challenge-waiting").classList.toggle("hidden", canAnswer);
      const choices = $("challenge-options");
      choices.replaceChildren();
      challenge.a.forEach((answer, index) => {
        const button = document.createElement("button");
        button.className = "choice";
        button.textContent = answer;
        button.disabled = !canAnswer;
        button.addEventListener("click", () => answerChallenge(index));
        choices.appendChild(button);
      });
      $("challenge").classList.remove("hidden");
    }

    function showLandingDecision() {
      const prompt = state.pending_landing;
      const purchaseIndex = state.pending_buy;
      if (!prompt && purchaseIndex === null) {
        $("property-decision").classList.add("hidden");
        return;
      }
      $("challenge").classList.add("hidden");
      const player = state.players[state.current];
      const canAct = Boolean(player && player.id === myPlayerId && socket.connected);
      const actions = $("property-decision-actions");
      actions.replaceChildren();
      let options;
      if (prompt) {
        const space = state.board[prompt.space];
        const owner = state.players.find((item) => item.id === prompt.owner);
        $("property-decision-badge").textContent = "ALUGUEL";
        $("property-decision-title").textContent = `${space.name} pertence a ${owner ? owner.name : "outro jogador"}.`;
        $("property-decision-detail").textContent = `Aluguel devido: ${money(prompt.amount)}. Pague agora ou tente um desafio para escapar.`;
        options = [
          {label: `Pagar aluguel · ${money(prompt.amount)}`, event: "monopoly_pay_rent"},
          {label: "Tentar um desafio", event: "monopoly_rent_challenge", secondary: true},
        ];
      } else {
        const space = state.board[purchaseIndex];
        const rent = space.rent === undefined ? "variável conforme os dados" : money(space.rent);
        const building = space.type === "property"
          ? `Construção: ${money(space.house_price)} por casa.`
          : "Este espaço não aceita construções.";
        $("property-decision-badge").textContent = "PROPRIEDADE DISPONÍVEL";
        $("property-decision-title").textContent = `Quer comprar ${space.name}?`;
        $("property-decision-detail").textContent = `Preço: ${money(space.price)} · Aluguel inicial: ${rent} · ${building}`;
        options = [
          {label: `Comprar ${space.name} · ${money(space.price)}`, event: "monopoly_buy"},
          {label: "Não comprar", event: "monopoly_pass", secondary: true},
        ];
      }
      options.forEach((option) => {
        const button = document.createElement("button");
        button.className = option.secondary ? "choice secondary" : "choice";
        button.textContent = option.label;
        button.disabled = !canAct;
        button.addEventListener("click", () => {
          actions.querySelectorAll("button").forEach((item) => { item.disabled = true; });
          socket.emit(option.event);
        });
        actions.appendChild(button);
      });
      $("property-decision-waiting").classList.toggle("hidden", canAct);
      $("property-decision").classList.remove("hidden");
    }

    function onGameState(payload) {
      const previousPositions = new Map(
        (state ? state.players : []).map((player) => [player.id, player.pos])
      );
      const playerIndexes = new Map(payload.players.map((player, index) => [player.id, index]));
      state = {
        ...payload,
        current: playerIndexes.get(payload.current) ?? -1,
        board: payload.board.map((space) => ({
          ...space,
          owner: space.owner === null ? null : playerIndexes.get(space.owner) ?? null,
        })),
      };
      const moves = payload.players.flatMap((player) => {
        const from = previousPositions.get(player.id);
        if (from === undefined || from === player.pos || player.bankrupt) return [];
        movingPawns.add(player.id);
        return [{
          id: player.id,
          from,
          to: player.pos,
          jailed: player.jailed && player.pos === 10,
          landing: (from + payload.dice[0] + payload.dice[1]) % initialBoard.length,
        }];
      });
      setScreen("game");
      $("leave-room").classList.remove("hidden");
      render();
      moves.forEach(animatePawn);
      showChallenge(payload.challenge);
      showLandingDecision();
      if (payload.phase === "finished") {
        const winner = payload.players.find((player) => player.id === payload.winner);
        $("winner-title").textContent = winner ? `${winner.name} venceu!` : "Partida encerrada";
        $("winner-copy").textContent = winner ? `A partida terminou com ${money(winner.money)}.` : "Todos os jogadores faliram.";
        $("game-over").classList.remove("hidden");
      } else {
        $("game-over").classList.add("hidden");
      }
    }

    $("create-room").addEventListener("click", () => {
      const name = $("player-name").value.trim();
      if (!name) return feedback("Digite seu nome antes de criar a sala.");
      socket.emit("create_room", {name});
    });
    $("join-room").addEventListener("click", () => {
      const name = $("player-name").value.trim();
      const code = $("join-code").value.trim().toUpperCase();
      if (!name) return feedback("Digite seu nome antes de entrar na sala.");
      if (!code) return feedback("Digite o código que recebeu.");
      socket.emit("join_room", {name, code});
    });
    $("join-code").addEventListener("input", (event) => {
      event.target.value = event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 5);
    });
    $("start-game").addEventListener("click", () => socket.emit("start_game"));
    $("leave-lobby").addEventListener("click", () => {
      socket.emit("leave_room");
      clearSession();
    });
    $("leave-room").addEventListener("click", () => {
      socket.emit("leave_room");
      clearSession();
    });
    $("copy-code").addEventListener("click", async () => {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText($("room-code").textContent);
        feedback("Código copiado. Envie-o aos seus amigos.", "feedback-lobby");
      } else {
        feedback(`Compartilhe este código: ${$("room-code").textContent}`, "feedback-lobby");
      }
    });
    $("game-over-close").addEventListener("click", () => $("game-over").classList.add("hidden"));

    $("chat-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const message = $("chat-input").value.trim();
      if (!message || !activeRoomCode || !socket.connected) return;
      socket.emit("chat_send", {message});
      $("chat-input").value = "";
      $("chat-input").focus();
    });

    socket.on("connect", () => {
      $("connection-status").textContent = "Conectado";
      setChatAvailable(Boolean(activeRoomCode));
      if (activeRoomCode && myToken) {
        socket.emit("rejoin_room", {code: activeRoomCode, token: myToken});
      }
    });
    socket.on("disconnect", () => {
      $("connection-status").textContent = "Reconectando...";
      setChatAvailable(false);
      if (state) render();
    });
    socket.on("connect_error", () => {
      $("connection-status").textContent = "Sem conexão com o servidor";
    });
    socket.on("room_joined", (data) => {
      saveSession(data.code, data.token, data.player_id);
      $("chat-room-label").textContent = `Sala ${data.code}`;
      setChatAvailable(socket.connected);
      feedback("");
    });
    socket.on("room_update", (room) => enterRoom(room));
    socket.on("chat_history", (data) => {
      $("chat-messages").replaceChildren();
      if (data.messages.length === 0) {
        const empty = document.createElement("div");
        empty.className = "chat-empty";
        empty.textContent = "Nenhuma mensagem ainda. Diga oi!";
        $("chat-messages").append(empty);
      } else {
        data.messages.forEach(appendChatMessage);
      }
    });
    socket.on("chat_message", appendChatMessage);
    socket.on("game_state", onGameState);
    socket.on("game_error", (data) => {
      if (!$("game-screen").classList.contains("hidden")) {
        $("status").textContent = data.message;
        if (state && (state.pending_landing || state.pending_buy !== null)) {
          showLandingDecision();
        }
      } else {
        const target = $("waiting-screen").classList.contains("hidden") ? "feedback" : "feedback-lobby";
        feedback(data.message, target);
      }
    });
    socket.on("session_expired", () => {
      clearSession();
      feedback("A sala não existe mais. Crie uma nova ou entre em outra.");
    });

    if (activeRoomCode && myToken) setScreen("waiting");
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE, board=BOARD)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=False)