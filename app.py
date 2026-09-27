from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
import random
import string
import time
from pathlib import Path

app = Flask(__name__)
app.config["SECRET_KEY"] = "tierlist-secret"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)

rooms = {}

TIERS = ["S", "A", "B", "C", "F"]

# Quantidade de rounds que cada jogador terá
TURNOS_POR_JOGADOR = 6

# Quantidade de rounds que cada tema fica ativo antes de trocar de tema
ROUNDS_POR_TEMA = 3

# Quantidade máxima de temas que cada jogador pode enviar por rodada
MAX_TEMAS_POR_JOGADOR = 3

# Catálogo simples de jogos
GAME_CATALOG = {
    "tier_guess": "Tier Guess",
    "acerte_tempo": "Acerte o Tempo",
}


def code():
    while True:
        c = ''.join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=5
            )
        )

        if c not in rooms:
            return c


def public_room(room):
    return {
        "code": room["code"],
        "host": room["host"],
        "players": [
            {
                "id": p["id"],
                "name": p["name"],
                "score": p.get("score", 0)
            }
            for p in room["players"].values()
        ],
        "waiting_player_count": len(room.get("waiting_players", {})),
        "started": room["started"],
        "phase": room.get("phase", "lobby"),
        "theme": room.get("theme"),
        "turn": room.get("turn"),
        "turn_number": room.get("turn_number", 0),
        "total_turns": room.get("total_turns", 0),
        # informações de jogo
        "current_game": room.get("current_game"),
        "game_phase": room.get("game_phase"),
        "previews": room.get("previews", {}),
        "duvide": room.get("duvide"),
        "acerte_tempo": (
            {
                "target": room["acerte_tempo"]["target"],
                "total": len(room["players"]),
            }
            if room.get("acerte_tempo")
            else None
        ),
    }


def broadcast_room(room):
    socketio.emit(
        "room_update",
        public_room(room),
        to=room["code"]
    )


def broadcast_rooms_list():
    """
    Emite a lista pública de salas (para exibição no cliente)
    """
    socketio.emit(
        "rooms_list",
        [public_room(r) for r in rooms.values()]
    )


def choose_letter():
    import string
    return random.choice([c for c in string.ascii_uppercase if c not in 'QV'])


def default_adedonha_categories():
    return ["Pessoa", "Animal", "País", "Comida"]


def next_player(room):
    ids = list(room["players"].keys())

    if not ids:
        return None

    idx = (room["turn_number"] - 1) % len(ids)

    return ids[idx]


def start_turn(room):
    """
    Inicia um novo round.
    O tema NÃO é alterado aqui.
    O tema só é escolhido quando todos enviam novos temas.
    """

    room["turn_number"] += 1
    room["theme_rounds_left"] = max(0, room.get("theme_rounds_left", 0) - 1)

    # Jogador que irá responder
    room["turn"] = next_player(room)

    # Tier secreto
    room["secret_tier"] = random.choice(TIERS)

    # Estado do round
    room["answer"] = None
    room["votes"] = {}
    room["confirmed_votes"] = {}
    room["submitted"] = False
    room["round_result"] = None
    room["round_result_deadline"] = None
    room["phase"] = "writing"

    # Envia informações para todos
    for sid in room["players"]:

        if sid == room["turn"]:

            socketio.emit(
                "your_turn",
                {
                    "theme": room["theme"],
                    "tier": room["secret_tier"],
                    "turn_number": room["turn_number"],
                },
                to=sid
            )

        else:

            socketio.emit(
                "waiting_turn",
                {
                    "theme": room["theme"],
                    "player": room["players"][room["turn"]]["name"],
                    "turn_number": room["turn_number"],
                },
                to=sid
            )

    broadcast_room(room)


def reset_room_to_lobby(room):
    """Reseta a partida para o lobby preservando pontuação da sala."""
    admit_waiting_players(room)
    room["started"] = False
    room["phase"] = "lobby"
    room["turn"] = None
    room["turn_number"] = 0
    room["total_turns"] = 0
    room["secret_tier"] = None
    room["answer"] = None
    room["votes"] = {}
    room["confirmed_votes"] = {}
    room["submitted"] = False
    room["theme"] = None
    room["theme_queue"] = []
    room["theme_rounds_left"] = 0
    room["theme_pool"] = []
    room["theme_usage"] = {}
    room["themes"] = {}
    room["current_game"] = None
    room["game_phase"] = None
    room.pop("acerte_tempo", None)
    room["pending_return_vote"] = False
    room["return_votes"] = {}
    broadcast_room(room)
    broadcast_rooms_list()


def normalize_theme_list(raw_theme):
    """Converte a entrada de temas em uma lista validada, até 3 itens."""
    raw_value = raw_theme or ""

    if isinstance(raw_value, str):
        pieces = [part.strip() for part in raw_value.replace("\n", ",").split(",")]
    else:
        pieces = []

    cleaned = []
    seen = set()
    for piece in pieces:
        theme = piece[:50].strip()
        if not theme:
            continue
        key = theme.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(theme)
        if len(cleaned) >= MAX_TEMAS_POR_JOGADOR:
            break

    return cleaned


def choose_next_theme(room):
    """Sorteia um tema da fila atual e mantém esse tema ativo por alguns rounds."""
    queue = list(room.get("theme_queue", []))
    if not queue:
        return room.get("theme")

    old_theme = room.get("theme")
    candidates = [theme for theme in queue if theme != old_theme]
    if not candidates:
        candidates = queue

    chosen = random.choice(candidates)
    room["theme_queue"] = [theme for theme in queue if theme != chosen]
    room["theme"] = chosen
    room["theme_rounds_left"] = ROUNDS_POR_TEMA
    room.setdefault("theme_usage", {})
    room["theme_usage"][chosen] = room["theme_usage"].get(chosen, 0) + 1
    return chosen


def all_themes_used_at_least_twice(room):
    """Verifica se todos os temas do ciclo já foram usados pelo menos 2 vezes."""
    theme_pool = room.get("theme_pool") or []
    if not theme_pool:
        return False

    usage = room.get("theme_usage", {})
    return all(usage.get(theme, 0) >= 2 for theme in theme_pool)


def start_theme_collection(room):
    """
    Coloca a partida na fase em que todos precisam
    enviar um novo tema.
    """

    room["phase"] = "themes"
    room["pending_return_vote"] = False
    room["return_votes"] = {}
    room["theme_queue"] = []
    room["theme_rounds_left"] = 0

    # Limpa os temas anteriores
    room["themes"] = {}

    # Avisa todos os jogadores
    socketio.emit(
        "show_theme_screen",
        {},
        to=room["code"]
    )

    # Atualiza o estado da sala
    broadcast_room(room)


def finish_theme_collection(room):
    """
    Quando todos enviaram seus temas, monta uma fila
    aleatória com os temas enviados e inicia o próximo round.
    """

    if not room["themes"]:
        return

    all_themes = []
    for submitted in room["themes"].values():
        all_themes.extend(submitted)

    if not all_themes:
        room["themes"] = {}
        return

    unique_themes = list(dict.fromkeys(all_themes))
    if not room.get("theme_pool"):
        room["theme_pool"] = unique_themes[:]

    random.shuffle(all_themes)
    room["theme_queue"] = all_themes[:]
    room["themes"] = {}
    choose_next_theme(room)

    # Começa o próximo round
    start_turn(room)


@app.route("/")
def index():
    # Passa o catálogo de jogos para o cliente renderizar na tela de lobby
    static_version = max(
        Path(app.static_folder, filename).stat().st_mtime_ns
        for filename in ("app.js", "style.css")
    )
    return render_template(
        "index.html",
        game_catalog=GAME_CATALOG,
        static_version=static_version,
    )


# ==========================================================
# CRIAR SALA
# ==========================================================

@socketio.on("create_room")
def create_room(data):

    name = (data.get("name") or "Jogador").strip()[:20]

    room_code = code()

    rooms[room_code] = {

        "code": room_code,

        "host": request.sid,

        "players": {
            request.sid: {
                "id": request.sid,
                "name": name,
                "score": 0,
                "token": data.get("token")
            }
        },

        "waiting_players": {},

        "started": False,

        # Temas enviados durante a fase de temas
        "themes": {},

        # Fila de temas para sorteio consecutivo por rodada
        "theme_queue": [],

        # Quantidade de rounds restantes para o tema atual
        "theme_rounds_left": 0,

        # Tema atualmente em uso
        "theme": None,

        "phase": "lobby",

        "turn": None,

        "turn_number": 0,

        "total_turns": 0,

        # Tier secreto do round
        "secret_tier": None,

        # Resposta do jogador
        "answer": None,

        # Votos
        "votes": {},
        # Previews e votos confirmados
        "previews": {},
        "confirmed_votes": {},

        "submitted": False,
        "round_result": None,
        "round_result_deadline": None,

        "chat_messages": [],
    }

    join_room(room_code)

    emit(
        "room_created",
        {
            "code": room_code
        }
    )
    emit("chat_history", {"messages": []}, to=request.sid)

    broadcast_room(rooms[room_code])
    broadcast_rooms_list()


# ==========================================================
# ENTRAR NA SALA
# ==========================================================

@socketio.on("join_room")
def join(data):

    room_code = (data.get("code") or "").upper().strip()

    name = (data.get("name") or "Jogador").strip()[:20]

    if room_code not in rooms:

        emit(
            "error_message",
            {
                "message": "Sala não encontrada."
            }
        )

        return

    room = rooms[room_code]

    waiting_for_round = False
    intermission = False
    can_join_acerte_tempo = (
        room.get("current_game") == "acerte_tempo"
        and room.get("game_phase") in ("acerte_tempo_playing", "acerte_tempo_finished")
    )
    can_join_tier_list = (
        room.get("current_game") == "tier_guess"
        and room.get("phase") in ("writing", "voting", "result", "themes")
    )
    waiting_for_round = (
        can_join_acerte_tempo and room.get("game_phase") == "acerte_tempo_playing"
    ) or (
        can_join_tier_list and room.get("phase") in ("writing", "voting", "themes")
    )
    intermission = (
        can_join_acerte_tempo and room.get("game_phase") == "acerte_tempo_finished"
    ) or (
        can_join_tier_list and room.get("phase") == "result"
    )
    if room["started"] and not (can_join_acerte_tempo or can_join_tier_list):

        emit(
            "error_message",
            {
                "message": "Essa partida já começou."
            }
        )

        return

    if len(room["players"]) + len(room.get("waiting_players", {})) >= 20:

        emit(
            "error_message",
            {
                "message": "A sala está cheia."
            }
        )

        return

    player = {
        "id": request.sid,
        "name": name,
        "score": 0,
        "token": data.get("token")
    }

    if waiting_for_round:
        room.setdefault("waiting_players", {})[request.sid] = player
    else:
        room["players"][request.sid] = player

    join_room(room_code)

    emit(
        "joined",
        {
            "code": room_code,
            "waiting": waiting_for_round,
            "intermission": intermission,
            "game": room.get("current_game"),
        }
    )
    emit("chat_history", {"messages": room.get("chat_messages", [])}, to=request.sid)

    if intermission:
        if room["current_game"] == "acerte_tempo":
            game = room["acerte_tempo"]
            result = dict(game["result"])
            result["scores"] = sorted(
                [
                    {"name": p["name"], "score": p["score"]}
                    for p in room["players"].values()
                ],
                key=lambda score: (-score["score"], score["name"].lower()),
            )
            result["seconds_remaining"] = max(
                0,
                int(game["next_round_at"] - time.monotonic() + 0.999),
            )
            emit("acerte_tempo_result", result, to=request.sid)
        else:
            result = dict(room["round_result"])
            result["scores"] = sorted(
                [
                    {"name": p["name"], "score": p["score"]}
                    for p in room["players"].values()
                ],
                key=lambda score: (-score["score"], score["name"].lower()),
            )
            result["seconds_remaining"] = max(
                0,
                int(room["round_result_deadline"] - time.monotonic() + 0.999),
            )
            emit("round_result", result, to=request.sid)
    elif waiting_for_round:
        emit(
            "waiting_room_update",
            {
                "players_waiting": len(room["waiting_players"]),
                "message": "Você entrou na sala de espera. Será incluído na próxima rodada.",
            },
            to=request.sid,
        )

    broadcast_room(room)
    broadcast_rooms_list()


@socketio.on("list_rooms")
def list_rooms():
    """Envia a lista pública de salas para o cliente que pediu."""
    socketio.emit(
        "rooms_list",
        [public_room(r) for r in rooms.values()],
        to=request.sid
    )


@socketio.on("chat_send")
def chat_send(data):
    room = rooms.get(data.get("code"))
    if (
        not room
        or (
            request.sid not in room["players"]
            and request.sid not in room.get("waiting_players", {})
        )
    ):
        return

    message = data.get("message")
    if not isinstance(message, str):
        emit("error_message", {"message": "Mensagem inválida."})
        return

    message = message.strip()[:300]
    if not message:
        emit("error_message", {"message": "Digite uma mensagem."})
        return

    chat_message = {
        "player": (
            room["players"].get(request.sid)
            or room["waiting_players"][request.sid]
        )["name"],
        "message": message,
        "time": time.strftime("%H:%M"),
    }
    room.setdefault("chat_messages", []).append(chat_message)
    room["chat_messages"] = room["chat_messages"][-100:]
    socketio.emit("chat_message", chat_message, to=room["code"])


# ==========================================================
# VOTAÇÃO DE JOGOS
# ==========================================================

@socketio.on("start_game_vote")
def start_game_vote(data):
    room = rooms.get(data.get("code"))
    if not room:
        return
    if request.sid != room["host"]:
        return

    # Define opções (padrão: todos os jogos do catálogo)
    options = data.get("options") or list(GAME_CATALOG.keys())

    room["game_options"] = options
    room["game_votes"] = {}
    room["game_phase"] = "voting"

    # Envia tela de votação para todos
    socketio.emit(
        "show_game_vote",
        {"options": [{"id": g, "name": GAME_CATALOG.get(g)} for g in options]},
        to=room["code"]
    )


@socketio.on("submit_game_vote")
def submit_game_vote(data):
    room = rooms.get(data.get("code"))
    if not room:
        return
    if room.get("game_phase") != "voting":
        return
    if request.sid not in room["players"]:
        return

    choice = data.get("game")
    if choice not in room.get("game_options", []):
        return

    room["game_votes"][request.sid] = choice

    # Atualiza status
    counts = {}
    for v in room["game_votes"].values():
        counts[v] = counts.get(v, 0) + 1

    socketio.emit(
        "game_vote_status",
        {"counts": counts, "total": len(room["players"]), "voted": len(room["game_votes"])},
        to=room["code"]
    )

    # Se todos votaram, decide e inicia o jogo
    if len(room["game_votes"]) == len(room["players"]):
        # escolhe por maioria simples; em empate randomicamente
        maxv = max(counts.values())
        winners = [g for g, c in counts.items() if c == maxv]
        selected = random.choice(winners)

        room["current_game"] = selected
        room["game_phase"] = "preparing"

        socketio.emit(
            "game_selected",
            {"game": selected, "name": GAME_CATALOG.get(selected)},
            to=room["code"]
        )

        # inicia o jogo
        start_game(room, selected)


def start_game(room, game_id):
    print(f"start_game invoked for room={room['code']} game_id={game_id}")
    # marca a sala como em partida para que os clientes não voltem ao lobby
    room["started"] = True
    room["phase"] = "playing"
    room["game_phase"] = "playing"

    socketio.emit(
        "start_game",
        {"game": game_id, "name": GAME_CATALOG.get(game_id)},
        to=room["code"]
    )

    if game_id == "acerte_tempo":
        start_acerte_tempo(room)
    else:
        # jogo padrão (tier guess) - inicia fluxo de temas/turnos (Tier Guess)
        room["current_game"] = "tier_guess"
        room["game_phase"] = "playing"
        # Inicia a coleta de temas para começar os rounds do Tier Guess
        start_theme_collection(room)


# ==========================================================
# MONOPOLY (mini-jogo simples)
# ==========================================================


def broadcast_monopoly(room):
    """Emite o estado atual do Monopoly para a sala."""
    socketio.emit("monopoly_state", room.get("monopoly", {}), to=room["code"])


def start_monopoly(room):
    """Inicializa uma partida simples de Monopoly para a sala.
    Versão simplificada: propriedades básicas, dinheiro inicial, pos, compra e aluguel.
    """

    # Tabuleiro simples (exemplo reduzido)
    board = [
        {"type": "go", "name": "Go"},
        {"type": "property", "name": "Mediterranean Ave", "price": 60, "rent": 2, "owner": None, "houses": 0, "hotel": False, "house_price": 50},
        {"type": "community", "name": "Community Chest"},
        {"type": "property", "name": "Baltic Ave", "price": 60, "rent": 4, "owner": None, "houses": 0, "hotel": False, "house_price": 50},
        {"type": "tax", "name": "Income Tax", "amount": 200},
        {"type": "railroad", "name": "Reading Railroad", "price": 200, "rent": 25, "owner": None, "house_price": 50},
        {"type": "property", "name": "Oriental Ave", "price": 100, "rent": 6, "owner": None, "houses": 0, "hotel": False, "house_price": 50},
        {"type": "chance", "name": "Chance"},
        {"type": "property", "name": "Vermont Ave", "price": 100, "rent": 6, "owner": None, "houses": 0, "hotel": False, "house_price": 50},
        {"type": "jail", "name": "Just Visiting / Jail"},
        {"type": "property", "name": "St. Charles Place", "price": 140, "rent": 10, "owner": None, "houses": 0, "hotel": False, "house_price": 70},
        {"type": "free_parking", "name": "Free Parking"}
    ]

    # Inicializa jogadores
    players_state = {}
    for sid, p in room["players"].items():
        players_state[sid] = {
            "id": sid,
            "name": p["name"],
            "pos": 0,
            "money": 1500,
            "properties": [],
            "in_jail": False
        }

    turn_order = list(room["players"].keys())

    room["current_game"] = "monopoly"
    room["game_phase"] = "playing"
    room["monopoly"] = {
        "board": board,
        "players": players_state,
        "turn_order": turn_order,
        "current_turn_idx": 0,
        "current_player": turn_order[0] if turn_order else None,
        "message": "Bem-vindo ao Monopoli!"
    }

    # Envia o estado inicial para todos
    socketio.emit("monopoly_start", room["monopoly"], to=room["code"])
    broadcast_monopoly(room)


@socketio.on("monopoly_roll")
def monopoly_roll(data):
    room = rooms.get(data.get("code"))
    if not room or room.get("current_game") != "monopoly":
        return

    m = room.get("monopoly")
    if not m:
        return

    sid = request.sid
    if sid != m.get("current_player"):
        # Não é a vez do jogador
        emit("error_message", {"message": "Não é sua vez."})
        return

    import random
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total = d1 + d2

    player = m["players"][sid]
    oldpos = player["pos"]
    newpos = (oldpos + total) % len(m["board"])

    # Passou pelo GO?
    if newpos < oldpos:
        player["money"] += 200

    player["pos"] = newpos
    space = m["board"][newpos]

    # Simples lógica de aluguel/compra
    landed = {
        "pos": newpos,
        "space": space,
        "dice": [d1, d2]
    }

    # Se propriedade e tiver dono -> pagar aluguel
    if space.get("type") in ("property", "railroad") and space.get("owner"):
        owner_id = space.get("owner")
        rent = space.get("rent") or max(1, int(space.get("price", 0) * 0.1))
        # Transferir rent
        pay = min(player["money"], rent)
        player["money"] -= pay
        m["players"][owner_id]["money"] += pay
        landed["rent_paid"] = pay
        landed["owner"] = m["players"][owner_id]["name"]

    # Se propriedade sem dono -> permitir compra (cliente pode chamar monopoly_buy)
    if space.get("type") in ("property", "railroad") and not space.get("owner"):
        landed["can_buy"] = True
        landed["price"] = space.get("price")

    m["last_landed"] = landed
    m["message"] = f"{player['name']} rolou {d1}+{d2} e foi para {space.get('name')}"

    broadcast_monopoly(room)
    socketio.emit("monopoly_roll_result", landed, to=room["code"]) 


@socketio.on("monopoly_build_house")
def monopoly_build_house(data):
    room = rooms.get(data.get("code"))
    if not room or room.get("current_game") != "monopoly":
        return
    m = room.get("monopoly")
    if not m:
        return

    sid = request.sid
    player = m["players"].get(sid)
    if not player:
        return

    pos = player["pos"]
    space = m["board"][pos]
    if space.get("type") not in ("property", "railroad"):
        emit("error_message", {"message": "Não é possível construir aqui."})
        return

    if space.get("owner") != sid:
        emit("error_message", {"message": "Você não é o dono desta propriedade."})
        return

    house_price = space.get("house_price", 50)
    hotel_price = house_price * 5

    # Se já tem hotel
    if space.get("hotel"):
        emit("error_message", {"message": "Já existe um hotel aqui."})
        return

    # Construir casa
    if space.get("houses", 0) < 4:
        if player["money"] < house_price:
            emit("error_message", {"message": "Dinheiro insuficiente para construir casa."})
            return
        player["money"] -= house_price
        space["houses"] = space.get("houses", 0) + 1
        m["message"] = f"{player['name']} construiu uma casa em {space.get('name')} por ${house_price}"
    else:
        # Constrói hotel (converte 4 casas em hotel)
        if player["money"] < hotel_price:
            emit("error_message", {"message": "Dinheiro insuficiente para construir hotel."})
            return
        player["money"] -= hotel_price
        space["houses"] = 0
        space["hotel"] = True
        m["message"] = f"{player['name']} construiu um hotel em {space.get('name')} por ${hotel_price}"

    broadcast_monopoly(room)


@socketio.on("monopoly_buy")
def monopoly_buy(data):
    room = rooms.get(data.get("code"))
    if not room or room.get("current_game") != "monopoly":
        return
    m = room.get("monopoly")
    if not m:
        return

    sid = request.sid
    player = m["players"].get(sid)
    if not player:
        return

    pos = player["pos"]
    space = m["board"][pos]
    if space.get("type") not in ("property", "railroad") or space.get("owner"):
        emit("error_message", {"message": "Propriedade não disponível para compra."})
        return

    price = space.get("price", 0)
    if player["money"] < price:
        emit("error_message", {"message": "Dinheiro insuficiente."})
        return

    player["money"] -= price
    space["owner"] = sid
    player["properties"].append(pos)
    m["message"] = f"{player['name']} comprou {space.get('name')} por ${price}"

    broadcast_monopoly(room)


@socketio.on("monopoly_end_turn")
def monopoly_end_turn(data):
    room = rooms.get(data.get("code"))
    if not room or room.get("current_game") != "monopoly":
        return
    m = room.get("monopoly")
    if not m:
        return

    sid = request.sid
    if sid != m.get("current_player"):
        emit("error_message", {"message": "Não é sua vez."})
        return

    # Avança o índice da vez
    idx = (m.get("current_turn_idx", 0) + 1) % max(1, len(m.get("turn_order", [])))
    m["current_turn_idx"] = idx
    m["current_player"] = m.get("turn_order", [])[idx]
    m["message"] = f"É a vez de {m['players'][m['current_player']]['name']}"

    broadcast_monopoly(room)


# ==========================================================
# HOST GAME SELECTION
# ==========================================================

@socketio.on("host_select_game")
def host_select_game(data):
    """Handler chamado quando o host seleciona um jogo diretamente no lobby.
    Apenas o host pode selecionar; isto marca current_game mas NÃO inicia o jogo.
    O host precisa então clicar em "começar" para iniciar de fato.
    """
    room = rooms.get(data.get("code"))
    if not room:
        return
    if request.sid != room.get("host"):
        return

    choice = data.get("game")
    if choice not in GAME_CATALOG:
        return

    room["current_game"] = choice
    room["game_phase"] = "preparing"

    socketio.emit(
        "game_selected",
        {"game": choice, "name": GAME_CATALOG.get(choice)},
        to=room["code"]
    )

    # Marca a seleção, mas NÃO inicia automaticamente — o host precisa clicar em INICIAR
    broadcast_room(room)


@socketio.on("host_start_game")
def host_start_game(data):
    """Handler chamado quando o host confirma o início do jogo selecionado.
    Valida que o host realmente selecionou um jogo e inicia o fluxo do jogo.
    """
    room = rooms.get(data.get("code"))
    if not room:
        return
    if request.sid != room.get("host"):
        return

    game = room.get("current_game")
    if not game:
        return
    if room.get("started"):
        return
    if game == "acerte_tempo" and len(room["players"]) < 2:
        emit("error_message", {"message": "É preciso ter pelo menos 2 jogadores."})
        return

    print(f"host_start_game received from {request.sid} for room {room['code']} game={game}")

    # Inicia o jogo escolhido
    start_game(room, game)
    print(f"start_game called for room {room['code']} game={game}")
    broadcast_room(room)


# ==========================================================
# IMPOSTOR
# ==========================================================

@socketio.on("start_themes")
def start_themes(data):

    room = rooms.get(data.get("code"))

    if not room:
        return

    if request.sid != room["host"]:
        return

    if room["started"]:
        return

    if len(room["players"]) < 2:

        emit(
            "error_message",
            {
                "message": "É preciso ter pelo menos 2 jogadores."
            }
        )

        return

    # Ao iniciar a partida, primeiro realizar votação do mini-jogo
    options = list(GAME_CATALOG.keys())
    room["game_options"] = options
    room["game_votes"] = {}
    room["game_phase"] = "voting"

    socketio.emit(
        "show_game_vote",
        {"options": [{"id": g, "name": GAME_CATALOG.get(g)} for g in options]},
        to=room["code"]
    )


# ==========================================================
# ENVIAR TEMA
# ==========================================================

@socketio.on("submit_theme")
def submit_theme(data):

    room_code = data.get("code")

    room = rooms.get(room_code)

    if not room:
        return

    # Só aceita temas durante a fase de temas
    if room.get("phase") != "themes":
        return

    # Jogador precisa estar na sala
    if request.sid not in room["players"]:
        return

    theme_list = normalize_theme_list(data.get("theme"))

    if not theme_list:

        emit(
            "error_message",
            {
                "message": "Digite pelo menos um tema válido."
            }
        )

        return

    # Salva/substitui os temas desse jogador (até 3)
    room["themes"][request.sid] = theme_list

    # Quantos já enviaram
    count = len(room["themes"])

    # Total de jogadores
    total = len(room["players"])

    # Atualiza todos
    socketio.emit(
        "theme_status",
        {
            "count": count,
            "total": total
        },
        to=room_code
    )

    # ======================================================
    # TODOS ENVIARAM
    # ======================================================

    if count == total:

        # Primeira vez iniciando a partida
        if not room["started"]:

            room["started"] = True

            room["total_turns"] = (
                len(room["players"])
                * TURNOS_POR_JOGADOR
            )

            room["turn_number"] = 0

            # Escolhe o primeiro tema usando a fila aleatória dos temas enviados
            all_themes = []
            for submitted in room["themes"].values():
                all_themes.extend(submitted)

            room["theme_queue"] = all_themes[:]
            room["themes"] = {}
            choose_next_theme(room)

            # Inicia o primeiro round
            start_turn(room)

        else:

            # Partida já estava acontecendo.
            # Então esses são novos temas.
            finish_theme_collection(room)


@socketio.on("request_return_to_lobby")
def request_return_to_lobby(data):
    room = rooms.get(data.get("code"))
    if not room:
        return
    if request.sid not in room["players"]:
        return
    # Allow requesting return to lobby during a started game as well
    if not room.get("started"):
        return

    room["pending_return_vote"] = True
    room["return_votes"] = {}
    socketio.emit(
        "return_to_lobby_prompt",
        {"message": "Voltar para o início?"},
        to=room["code"]
    )


@socketio.on("vote_return_to_lobby")
def vote_return_to_lobby(data):
    room = rooms.get(data.get("code"))
    if not room:
        return
    # allow voting to return during a started match
    if not room.get("started"):
        return
    if request.sid not in room["players"]:
        return
    if not room.get("pending_return_vote"):
        return

    choice = bool(data.get("choice"))
    room.setdefault("return_votes", {})[request.sid] = choice

    yes = sum(1 for v in room["return_votes"].values() if v)
    no = len(room["return_votes"]) - yes
    total = len(room["players"])

    socketio.emit(
        "return_to_lobby_vote_status",
        {"yes": yes, "no": no, "total": total},
        to=room["code"]
    )

    if yes > total / 2:
        room["pending_return_vote"] = False
        room["return_votes"] = {}
        socketio.emit("return_to_lobby_result", {"decision": "lobby"}, to=room["code"])
        reset_room_to_lobby(room)
        return

    if no > total / 2:
        room["pending_return_vote"] = False
        room["return_votes"] = {}
        socketio.emit("return_to_lobby_result", {"decision": "theme"}, to=room["code"])
        socketio.emit("show_theme_screen", {}, to=room["code"])
        broadcast_room(room)
        return


# ==========================================================
# ENVIAR RESPOSTA
# ==========================================================

@socketio.on("submit_answer")
def submit_answer(data):

    room = rooms.get(data.get("code"))

    if not room:
        return

    if room.get("turn") != request.sid:
        return

    if room.get("phase") != "writing":
        return

    answer = (data.get("answer") or "").strip()[:60]

    if not answer:

        emit(
            "error_message",
            {
                "message": "Digite uma resposta."
            }
        )

        return

    room["answer"] = answer

    room["phase"] = "voting"
    # reset confirmed votes when new voting starts
    room["confirmed_votes"] = {}

    socketio.emit(
        "show_answer",
        {
            "answer": answer,
            "author": room["players"][request.sid]["name"],
            "theme": room["theme"],
            "voters_total": max(
                0,
                len(room["players"]) - 1
            ),
        },
        to=room["code"]
    )


# ==========================================================
# VOTAR
# ==========================================================

@socketio.on("vote_preview")
def vote_preview(data):

    room = rooms.get(data.get("code"))
    if not room:
        return
    if room.get("phase") != "voting":
        return
    # Autor não pode enviar preview
    if request.sid == room["turn"]:
        return
    if request.sid not in room["players"]:
        return
    tier = data.get("tier")
    if tier not in TIERS:
        return
    voter = room["players"][request.sid]["name"]
    # Save preview so reconnections see it
    room.setdefault("previews", {})[request.sid] = tier

    socketio.emit(
        "vote_update",
        {
            "player_id": request.sid,
            "player": voter,
            "tier": tier,
            "votes": len(room.get("confirmed_votes", {})),
            "total": len(room["players"]) - 1,
            "preview": True,
        },
        to=room["code"]
    )

    # broadcast room so newcomers / reconnecting clients get preview state
    broadcast_room(room)


@socketio.on("vote")
def vote(data):

    room = rooms.get(data.get("code"))

    if not room:
        return

    if room.get("phase") != "voting":
        return

    # Autor não pode votar
    if request.sid == room["turn"]:
        return

    if request.sid not in room["players"]:
        return

    tier = data.get("tier")

    if tier not in TIERS:
        return

    # Salva o voto
    room["votes"][request.sid] = tier

    voter = room["players"][request.sid]["name"]

    # Mostra atualização dos votos
    socketio.emit(
        "vote_update",
        {
            "player_id": request.sid,
            "player": voter,
            "tier": tier,
            "votes": len(room["votes"]),
            "total": len(room["players"]) - 1,
        },
        to=room["code"]
    )

    # ======================================================
    # TODOS VOTARAM
    # ======================================================

    if len(room["votes"]) == len(room["players"]) - 1:

        author = room["turn"]

        correct = room["secret_tier"]

        author_hits = 0

        results = []

        # Calcula os votos
        for sid, selected in room["votes"].items():

            hit = selected == correct

            if hit:

                room["players"][sid]["score"] += 1

                author_hits += 1

            results.append(
                {
                    "player": room["players"][sid]["name"],
                    "tier": selected,
                    "correct": hit,
                    "score": room["players"][sid]["score"],
                }
            )

        # Autor ganha 2 pontos por cada acerto
        room["players"][author]["score"] += (
            author_hits * 2
        )

        room["phase"] = "result"
        admit_waiting_players(room)

        # Ranking
        scores = [
            {
                "name": p["name"],
                "score": p["score"]
            }
            for p in room["players"].values()
        ]

        scores.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        # Verifica se acabou a partida pelo critério de temas usados ao menos 2 vezes.
        game_over = all_themes_used_at_least_twice(room)

        room["round_result_deadline"] = time.monotonic() + 10
        room["round_result"] = {
            "answer": room["answer"],

            "author": room["players"][author]["name"],

            "correct": correct,

            "results": results,

            "scores": scores,

            "author_points": author_hits * 2,

            "hits": author_hits,

            "game_over": game_over,
            "seconds_remaining": 10,
        }
        socketio.emit("round_result", room["round_result"], to=room["code"])

        # Broadcast updated room so sidebars get latest scores
        broadcast_room(room)
        # Broadcast updated room so sidebars get latest scores
        broadcast_room(room)


# ==========================================================
# AVANÇAR AUTOMATICAMENTE
# ==========================================================


def finish_game(room):
    room["phase"] = "finished"
    scores = sorted(
        [
            {"name": p["name"], "score": p["score"]}
            for p in room["players"].values()
        ],
        key=lambda x: x["score"],
        reverse=True
    )
    socketio.emit(
        "game_finished",
        {"scores": scores},
        to=room["code"]
    )


def advance_round(room):
    if room.get("theme_rounds_left", 0) <= 0:
        if room.get("theme_queue"):
            choose_next_theme(room)
            start_turn(room)
            return

        if all_themes_used_at_least_twice(room):
            finish_game(room)
            return

        start_theme_collection(room)
        return

    if room.get("theme_queue") == [] and all_themes_used_at_least_twice(room):
        finish_game(room)
        return

    start_turn(room)


@socketio.on("auto_next_turn")
def auto_next_turn(data):

    room = rooms.get(data.get("code"))

    if not room:
        return

    if room.get("phase") != "result":
        return

    # Apenas o host controla o avanço
    if request.sid != room["host"]:
        return

    advance_round(room)


# ==========================================================
# PRÓXIMO TURNO MANUAL
# ==========================================================

@socketio.on("next_turn")
def next_turn(data):

    room = rooms.get(data.get("code"))

    if not room:
        return

    if room.get("phase") != "result":
        return

    # Apenas o host
    if request.sid != room["host"]:
        return

    advance_round(room)


# ==========================================================
# DESCONEXÃO
# ==========================================================

@socketio.on("disconnect")
def disconnect():

    for room_code, room in list(rooms.items()):

        if request.sid in room.get("waiting_players", {}):
            del room["waiting_players"][request.sid]
            broadcast_room(room)
            broadcast_rooms_list()
            continue

        if request.sid not in room["players"]:
            continue

        # Remove jogador
        del room["players"][request.sid]

        # Remove any previews or confirmed votes from this player
        room.get("previews", {}).pop(request.sid, None)
        room.get("confirmed_votes", {}).pop(request.sid, None)
        room.get("votes", {}).pop(request.sid, None)
        room.get("acerte_tempo", {}).get("guesses", {}).pop(request.sid, None)
        room.get("acerte_tempo", {}).get("timer_starts", {}).pop(request.sid, None)

        # Remove tema dele
        room["themes"].pop(request.sid, None)

        # Se não houver mais jogadores
        if not room["players"]:
            if room.get("current_game") == "acerte_tempo" and room.get("waiting_players"):
                admit_waiting_players(room)
                start_acerte_tempo(room)
            else:
                del rooms[room_code]
            continue

        # Se o host saiu
        if room["host"] == request.sid:

            room["host"] = next(
                iter(room["players"])
            )

        if (
            room.get("current_game") == "acerte_tempo"
            and room.get("game_phase") == "acerte_tempo_playing"
            and room["players"]
            and len(room["acerte_tempo"]["guesses"]) == len(room["players"])
        ):
            finish_acerte_tempo_round(room)

        # Se o jogador que estava respondendo saiu
        if (
            room.get("turn") == request.sid
            and room.get("started")
            and room.get("phase") not in [
                "finished",
                "themes"
            ]
        ):

            if (
                room["turn_number"]
                < room.get("total_turns", 0)
            ):

                start_turn(room)

        broadcast_room(room)
        broadcast_rooms_list()


# ==========================================================
# DUVIDE (modo de tempo oculto)
# ==========================================================


def start_acerte_tempo(room):
    room["current_game"] = "acerte_tempo"
    room["phase"] = "acerte_tempo"
    room["game_phase"] = "acerte_tempo_playing"
    room["acerte_tempo"] = {
        "target": random.randint(500, 10000) / 1000,
        "timer_starts": {},
        "guesses": {},
    }
    socketio.emit(
        "acerte_tempo_start",
        {"target": room["acerte_tempo"]["target"], "total": len(room["players"])},
        to=room["code"],
    )
    broadcast_room(room)


def admit_waiting_players(room):
    waiting_players = room.get("waiting_players", {})
    if not waiting_players:
        return

    for sid, player in list(waiting_players.items()):
        room["players"][sid] = player
        socketio.emit("late_player_admitted", {}, to=sid)
    waiting_players.clear()
    broadcast_room(room)
    broadcast_rooms_list()


def finish_acerte_tempo_round(room):
    game = room["acerte_tempo"]
    target = game["target"]
    guesses = game["guesses"]
    if not guesses:
        return

    differences = {
        sid: abs(elapsed - target)
        for sid, elapsed in guesses.items()
    }
    best_difference = min(differences.values())
    winners = {
        sid for sid, difference in differences.items()
        if difference == best_difference
    }

    results = []
    for sid, elapsed in guesses.items():
        is_winner = sid in winners
        if is_winner:
            room["players"][sid]["score"] += 1
        results.append({
            "player": room["players"][sid]["name"],
            "guess": elapsed,
            "difference": differences[sid],
            "winner": is_winner,
        })
    results.sort(key=lambda result: (result["difference"], result["player"].lower()))
    game["status"] = "finished"
    room["game_phase"] = "acerte_tempo_finished"

    scores = sorted(
        [
            {"name": player["name"], "score": player["score"]}
            for player in room["players"].values()
        ],
        key=lambda player: (-player["score"], player["name"].lower()),
    )
    game["result"] = {
        "target": target,
        "results": results,
        "scores": scores,
        "seconds_remaining": 8,
    }
    game["next_round_at"] = time.monotonic() + 8
    socketio.emit("acerte_tempo_result", game["result"], to=room["code"])
    broadcast_room(room)
    socketio.start_background_task(start_next_acerte_tempo_round, room, game)


def start_next_acerte_tempo_round(room, finished_game):
    socketio.sleep(max(0, finished_game["next_round_at"] - time.monotonic()))
    if (
        room.get("acerte_tempo") is finished_game
        and room.get("current_game") == "acerte_tempo"
        and room.get("game_phase") == "acerte_tempo_finished"
        and room.get("players")
    ):
        admit_waiting_players(room)
        start_acerte_tempo(room)


@socketio.on("acerte_tempo_begin")
def acerte_tempo_begin(data):
    room = rooms.get(data.get("code"))
    if (
        not room
        or room.get("current_game") != "acerte_tempo"
        or room.get("game_phase") != "acerte_tempo_playing"
    ):
        return {"ok": False, "message": "A rodada não está disponível para iniciar."}
    if request.sid not in room["players"]:
        return {"ok": False, "message": "Você não está nesta sala."}

    game = room["acerte_tempo"]
    if request.sid in game["guesses"]:
        return {"ok": False, "message": "Seu tempo já foi confirmado."}
    if request.sid in game["timer_starts"]:
        return {"ok": True, "running": True}

    game["timer_starts"][request.sid] = time.monotonic()
    return {"ok": True}


@socketio.on("acerte_tempo_stop")
def acerte_tempo_stop(data):
    room = rooms.get(data.get("code"))
    if (
        not room
        or room.get("current_game") != "acerte_tempo"
        or room.get("game_phase") != "acerte_tempo_playing"
    ):
        return {"ok": False, "message": "A rodada não está disponível para parar."}
    if request.sid not in room["players"]:
        return {"ok": False, "message": "Você não está nesta sala."}

    game = room["acerte_tempo"]
    if request.sid in game["guesses"]:
        return {"ok": True, "submitted": True, "elapsed": game["guesses"][request.sid]}

    started_at = game["timer_starts"].get(request.sid)
    if started_at is None:
        return {"ok": False, "message": "Toque em iniciar antes de parar o cronômetro."}

    elapsed = round(time.monotonic() - started_at, 3)
    game["guesses"][request.sid] = elapsed
    socketio.emit(
        "acerte_tempo_progress",
        {"submitted": len(game["guesses"]), "total": len(room["players"])},
        to=room["code"],
    )

    if len(game["guesses"]) == len(room["players"]):
        finish_acerte_tempo_round(room)
    return {"ok": True, "elapsed": elapsed}


def start_duvide(room):
    """Inicia o mini-jogo Duvide: cada jogador chuta um tempo em segundos,
    mas o tempo real só aparece depois do countdown oculto terminar."""
    room["current_game"] = "duvide"
    room["phase"] = "duvide"
    room["game_phase"] = "duvide_waiting"
    room["duvide"] = {
        "status": "waiting_guesses",
        "guesses": {},
        "target": None,
        "started_at": None,
    }

    socketio.emit(
        "duvide_start",
        {
            "phase": "waiting_guesses",
            "message": "Chute um tempo em segundos e envie seu palpite.",
            "min": 1,
            "max": 60,
        },
        to=room["code"],
    )
    broadcast_room(room)


@socketio.on("duvide_submit_guess")
def duvide_submit_guess(data):
    room = rooms.get(data.get("code"))
    if not room or room.get("current_game") != "duvide":
        return

    if request.sid not in room["players"]:
        return

    d = room.get("duvide") or {}
    if d.get("status") != "waiting_guesses":
        return

    try:
        guess = int(data.get("guess"))
    except (TypeError, ValueError):
        emit("error_message", {"message": "Digite um número válido de segundos."})
        return

    if guess < 1 or guess > 60:
        emit("error_message", {"message": "O tempo deve estar entre 1 e 60 segundos."})
        return

    d["guesses"][request.sid] = guess
    socketio.emit(
        "duvide_guess_status",
        {
            "player": room["players"][request.sid]["name"],
            "guess": guess,
            "count": len(d["guesses"]),
            "total": len(room["players"]),
        },
        to=room["code"],
    )

    if len(d["guesses"]) == len(room["players"]):
        target = random.randint(3, 30)
        d["status"] = "running"
        d["target"] = target
        d["started_at"] = time.time()

        socketio.emit(
            "duvide_hidden_timer",
            {
                "phase": "running",
                "message": "Tempo escondido em execução. Não revele o relógio na tela.",
                "target": target,
            },
            to=room["code"],
        )

        socketio.start_background_task(_finish_duvide_round, room)


def _finish_duvide_round(room):
    d = room.get("duvide") or {}
    if not d:
        return

    target = d.get("target")
    if target is None:
        return

    time.sleep(max(1, int(target)))

    results = []
    best = None
    for sid, guess in d.get("guesses", {}).items():
        diff = abs(int(guess) - int(target))
        if best is None or diff < best:
            best = diff
        results.append({
            "player": room["players"][sid]["name"],
            "guess": int(guess),
            "difference": diff,
        })

    ranking = sorted(results, key=lambda item: (item["difference"], -item["guess"]))
    for item in ranking:
        player_name = item["player"]
        sid = next((k for k, p in room["players"].items() if p["name"] == player_name), None)
        if sid is None:
            continue
        if item["difference"] == best:
            room["players"][sid]["score"] += 3
        else:
            room["players"][sid]["score"] += max(0, 2 - item["difference"])

    room["duvide"] = {
        "status": "finished",
        "guesses": d.get("guesses", {}),
        "target": target,
        "results": ranking,
    }

    socketio.emit(
        "duvide_result",
        {
            "target": target,
            "results": ranking,
            "winner": ranking[0]["player"] if ranking else None,
            "scores": [
                {"name": p["name"], "score": p["score"]}
                for p in room["players"].values()
            ],
        },
        to=room["code"],
    )

    room["current_game"] = None
    room["game_phase"] = None
    broadcast_room(room)
    broadcast_rooms_list()


# ==========================================================
# IMPOSTOR (continuação)
# ==========================================================

IMPOSTOR_WORDS = [
    "gato", "cachorro", "passaro", "peixe", "leão", "tigre", "elefante", "cavalo", "vaca", "ovelha",
    "porco", "galinha", "macaco", "coelho", "urso", "raposa", "girafa", "zebra", "canguru", "golfinho",
    "tubarao", "polvo", "baleia", "camarão", "lagosta", "caranguejo", "aranha", "borboleta", "abelha", "formiga",
    "maçã", "banana", "laranja", "uva", "manga", "abacaxi", "pera", "morango", "melancia", "kiwi",
    "limão", "cereja", "pêssego", "tomate", "batata", "cenoura", "alface", "cebola", "alho", "pimentão",
    "arroz", "feijão", "macarrão", "pizza", "hambúrguer", "sushi", "churrasco", "sopa", "bolo", "biscoito",
    "sorvete", "chocolate", "café", "chá", "suco", "leite", "queijo", "iogurte", "manteiga", "pão",
    "carro", "ônibus", "trem", "bicicleta", "moto", "avião", "helicóptero", "barco", "navio", "metrô",
    "ônibus escolar", "caminhão", "carreta", "trator", "carroça", "skate", "patins", "balão", "nave", "foguete",
    "computador", "telefone", "tablet", "televisão", "rádio", "relógio", "câmera", "fones", "carregador", "impressora",
    "livro", "revista", "jornal", "caderno", "caneta", "lápis", "borracha", "tesoura", "cola", "mochila",
    "praia", "montanha", "floresta", "deserto", "ilha", "rio", "lago", "cachoeira", "cidade", "vila",
    "castelo", "museu", "parque", "cinema", "teatro", "estádio", "escola", "universidade", "hospital", "igreja",
    "música", "filme", "jogo", "brinquedo", "pintura", "escultura", "poesia", "dança", "teatro", "fotografia",
    "vermelho", "azul", "verde", "amarelo", "preto", "branco", "laranja_cor", "rosa", "roxo", "marrom",
    "quente", "frio", "doce", "salgado", "amargo", "azedo", "macio", "duro", "leve", "pesado"
]


def start_impostor(room):
    # escolhe palavra comum
    common = random.choice(IMPOSTOR_WORDS)
    # escolhe impostor
    pids = list(room["players"].keys())
    impostor = random.choice(pids)

    room["impostor_data"] = {
        "common": common,
        "impostor": impostor,
        "word_map": {},
        "hints": {},
        "votes": {}
    }

    print(f"start_impostor: room={room['code']} impostor={impostor} common='{common}'")

    for sid in pids:
        if sid == impostor:
            # impostor recebe palavra diferente (não informamos nada sobre ser impostor)
            w = random.choice([w for w in IMPOSTOR_WORDS if w != common])
            room["impostor_data"]["word_map"][sid] = w
            print(f"sending impostor_start to impostor {sid} word='{w}'")
            socketio.emit("impostor_start", {"your_word": w}, to=sid)
        else:
            room["impostor_data"]["word_map"][sid] = common
            print(f"sending impostor_start to player {sid} word='{common}'")
            socketio.emit("impostor_start", {"your_word": common}, to=sid)


@socketio.on("impostor_submit_hint")
def impostor_submit_hint(data):
    room = rooms.get(data.get("code"))
    if not room: return
    if request.sid not in room["players"]: return

    d = room.get("impostor_data")
    if not d: return

    hint = (data.get("hint") or "").strip()[:120]
    d["hints"][request.sid] = hint

    # emite atualização imediata para o chat de dicas (append)
    player_name = room["players"][request.sid]["name"]
    socketio.emit("impostor_hint_update", {"player": player_name, "hint": hint}, to=room["code"])

    # quando todos enviarem hints, também envia agregação completa (compatibilidade)
    if len(d["hints"]) == len(room["players"]):
        hints_pub = [{"player": room["players"][sid]["name"], "hint": h} for sid, h in d["hints"].items()]
        socketio.emit("impostor_hints", {"hints": hints_pub}, to=room["code"])

        # inicia fase de votação específica para impostor
        d["votes"] = {}  # sid -> target or 'skip'
        room["game_phase"] = "impostor_voting"

        # lista de opções (players) e threshold de eliminação
        player_list = [{"id": sid, "name": room["players"][sid]["name"]} for sid in room["players"]]
        total_players = len(player_list)
        threshold = (75 * total_players + 99) // 100  # ceil(0.75 * total)

        socketio.emit(
            "impostor_show_voting",
            {"players": player_list, "threshold": threshold, "total": total_players},
            to=room["code"]
        )


@socketio.on("impostor_vote")
def impostor_vote(data):
    room = rooms.get(data.get("code"))
    if not room: return
    d = room.get("impostor_data")
    if not d: return

    target = data.get("target")
    # allow 'skip' as a target
    if target != "skip" and target not in room["players"]:
        return

    d["votes"][request.sid] = target

    # broadcast live vote counts
    counts = {}
    for t in d["votes"].values():
        counts[t] = counts.get(t, 0) + 1

    # build human-readable counts map
    counts_named = {}
    for k, v in counts.items():
        if k == "skip":
            counts_named["skip"] = v
        else:
            pname = room["players"].get(k, {}).get("name", k)
            counts_named[pname] = v

    socketio.emit("impostor_vote_update", {"counts": counts_named, "voted": len(d["votes"]), "total": len(room["players"])}, to=room["code"])

    # check 75% elimination threshold
    total = len(room["players"])
    needed = (75 * total + 99) // 100

    # check if any target reached threshold
    for tgt, c in counts.items():
        if c >= needed:
            picked = None if tgt == "skip" else tgt
            impostor = d["impostor"]
            success = (picked == impostor)

            # regra nova: o jogo só termina quando eliminam o impostor.
            # se erram, todos perdem e o impostor ganha +2.
            # se acertam, os não-impostores ganham +1 cada.
            if success:
                for sid in room["players"]:
                    if sid != impostor:
                        room["players"][sid]["score"] += 1
            else:
                room["players"][impostor]["score"] += 2

            socketio.emit(
                "impostor_result",
                {"picked": picked, "impostor": impostor, "success": success, "by_threshold": True},
                to=room["code"]
            )
            room.pop("impostor_data", None)
            room["current_game"] = None
            room["game_phase"] = None
            broadcast_room(room)
            broadcast_rooms_list()
            return

    # if all voted and no threshold reached, fallback to majority
    if len(d["votes"]) == len(room["players"]):
        picked = max(counts.items(), key=lambda x: x[1])[0]
        picked = None if picked == "skip" else picked
        impostor = d["impostor"]
        success = (picked == impostor)

        if success:
            for sid in room["players"]:
                if sid != impostor:
                    room["players"][sid]["score"] += 1
        else:
            room["players"][impostor]["score"] += 2

        socketio.emit(
            "impostor_result",
            {"picked": picked, "impostor": impostor, "success": success, "by_threshold": False},
            to=room["code"]
        )
        room.pop("impostor_data", None)
        room["current_game"] = None
        room["game_phase"] = None
        broadcast_room(room)
        broadcast_rooms_list()


# ==========================================================
# ADEDONHA
# ==========================================================


def start_adedonha(room):
    letter = choose_letter()
    categories = default_adedonha_categories()

    room["adedonha_data"] = {
        "letter": letter,
        "categories": categories,
        "submissions": {},
        "results": None
    }

    socketio.emit("adedonha_start", {"letter": letter, "categories": categories}, to=room["code"])


@socketio.on("adedonha_submit")
def adedonha_submit(data):
    room = rooms.get(data.get("code"))
    if not room: return
    d = room.get("adedonha_data")
    if not d: return

    answers = data.get("answers") or {}
    # store per player
    d["submissions"][request.sid] = answers

    if len(d["submissions"]) == len(room["players"]):
        # compute scores using new rule:
        # For each category, if multiple players submitted the same valid word -> each of those players gets 1 point for that category.
        # If no players submitted the same word (i.e., all valid answers are unique) -> each player with a valid answer gets 2 points for that category.
        results = {}
        categories = d["categories"]

        # prepare normalized answers per category
        per_cat = {cat: [] for cat in categories}
        for sid, answers in d["submissions"].items():
            for cat in categories:
                ans = (answers.get(cat) or "").strip()
                per_cat[cat].append((sid, ans))

        # initialize player scores for this round
        round_scores = {sid: 0 for sid in room["players"]}
        round_answers = {room["players"][sid]["name"]: {} for sid in room["players"]}

        for cat in categories:
            entries = per_cat[cat]
            # count valid answers that start with the letter
            valid_entries = [(sid, ans) for sid, ans in entries if ans and ans[0].upper() == d["letter"]]
            # normalize for comparison
            norm_map = {}
            for sid, ans in valid_entries:
                key = ans.strip().lower()
                norm_map.setdefault(key, []).append((sid, ans))

            if not valid_entries:
                continue

            # if a given normalized key has count >1 -> those players get 1 point each
            # if a normalized key has count ==1 and there is no other matching keys (i.e., all unique) -> that player gets 2 points
            # But the rule says: if words are equal each gets 1, if none are equal each gets 2 (per word)
            # This implies: if all valid answers for this category are unique => everyone with valid answer gets 2; else players in groups get 1 for their group
            if all(len(v) == 1 for v in norm_map.values()):
                # all unique
                for key, items in norm_map.items():
                    sid, ans = items[0]
                    round_scores[sid] += 2
            else:
                for key, items in norm_map.items():
                    if len(items) > 1:
                        for sid, ans in items:
                            round_scores[sid] += 1
                    else:
                        # unique among others but there exist duplicates elsewhere -> unique gets 0? The user's rule: if words are equal each gets 1; if none equal each gets 2
                        # ambiguous for mixed case; choose to give 1 to duplicates and 2 to uniques only if ALL are unique. Otherwise uniques get 1? To be fair, give 1 for duplicates and 1 for uniques as well.
                        # But user's text: "se as palavras forem iguais cada um ganha 1 ponto se nenhuma palavra for igual cada um ganha 2 (isso por cada palavra)"
                        # For mixed case, interpret that duplicates get 1, uniques get 0? That seems odd. Safer: duplicates get 1, uniques get 1 as well (so duplicates and uniques get 1) — but then no incentive.
                        # Choose: duplicates get 1, uniques get 1 as well (same as duplicates) — however user likely intended unique gets 2 only if all are unique. We'll implement: if not all unique, duplicates get 1, uniques get 1.
                        sid, ans = items[0]
                        round_scores[sid] += 1

            # record answers for display
            for sid, ans in entries:
                round_answers[room["players"][sid]["name"]][cat] = ans

        # commit scores
        for sid, sc in round_scores.items():
            room["players"][sid]["score"] += sc
            results[room["players"][sid]["name"]] = sc

        d["results"] = {"scores": results, "answers": round_answers}
        socketio.emit("adedonha_results", d["results"], to=room["code"])
        room.pop("adedonha_data", None)
        room["current_game"] = None
        room["game_phase"] = None
        broadcast_room(room)
        broadcast_rooms_list()


# ==========================================================
# QUEM SOU EU (novo fluxo)
# ==========================================================

# No novo fluxo, cada jogador envia um nome (qualquer pessoa, não pode ser ele mesmo).
# Os nomes são embaralhados (derangement) para não atribuir o próprio nome ao autor.
# Em cada turno, todos exceto o alvo enviam UMA dica (<=5 palavras ou <=25 caracteres) sem mencionar o nome.


def make_derangement(names):
    # names: list of strings in submitter order
    # returns a shuffled list where no element is in the original position (derangement).
    if len(names) == 1:
        return names[:]  # no derangement possible; fallback

    attempts = 0
    while True:
        shuffled = names[:]
        random.shuffle(shuffled)
        valid = True
        for i in range(len(names)):
            if shuffled[i].strip().lower() == names[i].strip().lower():
                valid = False
                break
        if valid:
            return shuffled
        attempts += 1
        if attempts > 200:
            # fallback to rotate by 1
            return names[1:] + names[:1]




# ==========================================================
# INICIAR SERVIDOR
# ==========================================================

if __name__ == "__main__":

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )
