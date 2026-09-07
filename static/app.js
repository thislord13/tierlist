const socket = io();
let myId = null;
let roomCode = null;
let isHost = false;
let myTurn = false;
let selectedVoteTier = null;

// Pequenas funções para ler/gravar cookies
function getCookie(name) {
  const v = document.cookie.match('(?:^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return v ? decodeURIComponent(v[1]) : null;
}
function setCookie(name, value, days) {
  let expires = "";
  if (days) {
    const d = new Date();
    d.setTime(d.getTime() + (days*24*60*60*1000));
    expires = "; expires=" + d.toUTCString();
  }
  document.cookie = name + "=" + encodeURIComponent(value) + expires + "; path=/";
}

// Token persistente do jogador (armazenado em cookie) para identificar o cliente localmente
let playerToken = getCookie('player_token');
if (!playerToken) {
  playerToken = Math.random().toString(36).slice(2, 10) + Math.random().toString(36).slice(2, 10);
  setCookie('player_token', playerToken, 365);
}

// Prefill do nome se houver cookie
let savedName = getCookie('player_name');
if (savedName) {
  const ni = document.getElementById('nameInput');
  if (ni) ni.value = savedName;
}

function show(id) {
  document.querySelectorAll(".screen").forEach(x => x.classList.remove("active"));
  document.getElementById(id).classList.add("active");
}

function error(msg) {
  const el = document.getElementById("error");
  el.textContent = msg;
  el.style.display = "block";
  setTimeout(() => el.style.display = "none", 3000);
}

function name() {
  return document.getElementById("nameInput").value.trim() || "Jogador";
}

function createRoom() {
  const n = name();
  setCookie('player_name', n, 365);
  socket.emit("create_room", {name: n, token: playerToken});
}

function showJoin() {
  show("join");
}

function joinRoom() {
  const n = name();
  setCookie('player_name', n, 365);
  const code = document.getElementById("joinCode").value.trim().toUpperCase();
  if (!code) return error("Digite o código da sala.");
  socket.emit("join_room", {name: n, code, token: playerToken});
}

socket.on("connect", () => { myId = socket.id; socket.emit('list_rooms'); });

socket.on("room_created", data => {
  roomCode = data.code;
  document.getElementById("roomLabel").textContent = "Sala " + roomCode;
  document.getElementById("codeBig").textContent = roomCode;
  show("lobby");
});

socket.on("joined", data => {
  roomCode = data.code;
  document.getElementById("roomLabel").textContent = "Sala " + roomCode;
  show("lobby");
});

socket.on("error_message", data => error(data.message));

function renderLobbyHostControls(room) {
  isHost = room.host === myId;
  const hostStartEl = document.getElementById("hostStart");
  const gameControlEl = document.getElementById("gameControl");

  if (!hostStartEl || !gameControlEl) return;

  if (isHost) {
    if (room.players.length >= 2) {
      // Removido botões pequenos; instrução para usar o botão INICIAR grande abaixo
      hostStartEl.innerHTML = '<p style="margin:6px 0;">Use o botão <b>INICIAR</b> abaixo para começar o jogo selecionado.</p>';
    } else {
      hostStartEl.innerHTML = '<p>É preciso ter pelo menos 2 jogadores.</p>';
    }
  } else {
    hostStartEl.innerHTML = '<p>Aguardando o anfitrião...</p>';
  }

  gameControlEl.innerHTML = '';
}

socket.on("room_update", room => {
  window.currentRoom = room;
  roomCode = room.code;
  isHost = room.host === myId;
  window.lastSelectedGame = room.current_game || null;
  window.lastStartedGame = room.started && room.current_game ? room.current_game : null;
  document.getElementById("roomLabel").textContent = "Sala " + room.code;
  document.getElementById("codeBig").textContent = room.code;

  document.getElementById("players").innerHTML = room.players.map(p =>
    `<div class="player"><span>👤 ${escapeHtml(p.name)}</span> <b>${p.score || 0} pts</b></div>`
  ).join("");

  // Atualiza sidebar de placar (se existir)
  if (typeof updateScoreSidebar === 'function') updateScoreSidebar(room);

  // Mostrar/ocultar botão de retorno ao lobby (header + floating) durante a partida
  const rb = document.getElementById('returnLobbyBtn');
  const rf = document.getElementById('returnLobbyFloating');
  const riV = document.getElementById('returnLobbyInlineVoting');
  const riW = document.getElementById('returnLobbyInlineWaiting');
  if (rb) rb.style.display = room.started ? 'inline-block' : 'none';
  if (rf) rf.style.display = room.started ? 'inline-block' : 'none';
  if (riV) riV.style.display = room.started ? 'inline-block' : 'none';
  if (riW) riW.style.display = room.started ? 'inline-block' : 'none';

  if (!room.started && room.phase === "lobby") {
    show("lobby");
    renderLobbyHostControls(room);
  }

  if (room.phase === "themes") {
    show("theme");
  }

  // Atualiza a visualização dos jogos na tela de lobby (inclui ícone de mão para sua escolha)
  renderLobbyGames(room);
});

// Atualização da lista de salas públicas
socket.on("rooms_list", rooms => {
  const el = document.getElementById("roomsList");
  if (!el) return;
  if (!rooms || rooms.length === 0) {
    el.innerHTML = '<p>Nenhuma sala disponível.</p>';
    return;
  }

  el.innerHTML = rooms.map(r => {
    const players = (r.players || []).map(p => `<span class="mini-player">👤 ${escapeHtml(p.name)}</span>`).join(' ');
    return `
      <div class="room-item">
        <div><strong>${r.code}</strong> — ${r.players.length} jogador(s)</div>
        <div class="room-players">${players}</div>
        <div><button onclick="document.getElementById('joinCode').value='${r.code}'; show('join');">Entrar</button></div>
      </div>
    `;
  }).join('');
});

socket.on("theme_status", data => {
  document.getElementById("themeStatus").textContent =
    `${data.count}/${data.total} jogadores enviaram seus temas.`;
});

socket.on("show_theme_screen", () => {
  const input = document.getElementById("themeInput");
  const button = document.querySelector("#theme button");
  if (input) {
    input.disabled = false;
    input.value = "";
  }
  if (button) button.disabled = false;
  show("theme");
});

socket.on("your_turn", data => {
  myTurn = true;
  document.getElementById("myTier").textContent = data.tier;
  document.getElementById("writeTheme").textContent = "Tema: " + data.theme;
  document.getElementById("answerInput").value = "";
  show("writing");
});

socket.on("waiting_turn", data => {
  myTurn = false;
  document.getElementById("currentPlayer").textContent = data.player;
  document.getElementById("waitingTheme").textContent = "Tema: " + data.theme;
  show("waiting");
});

socket.on("show_answer", data => {
  myTurn = false;
  selectedVoteTier = null;
  document.getElementById("voteTheme").textContent = data.theme;
  document.getElementById("answerBig").textContent = data.answer;
  document.getElementById("answerAuthor").textContent = "👤 " + data.author;
  buildTierList();
  document.getElementById("voteCount").textContent = `0/${data.voters_total} votos`;
  show("voting");
});

function buildTierList() {
  const list = document.getElementById("tierList");
  list.innerHTML = ["S","A","B","C","F"].map(t =>
  `<div class="tier-row" data-tier="${t}">
    <div class="tier-label" onclick="selectTier('${t}')">${t}</div>
    <div class="tier-area" id="tier-${t}" onclick="selectTier('${t}')"></div>
    </div>`
  ).join("");
  updateVoteButtonState();
  // after rebuilding tier list, render any existing previews from currentRoom
  if (window.currentRoom && window.currentRoom.previews) {
    renderPreviewsFromRoom(window.currentRoom.previews);
  }
}

function selectTier(tier) {
  selectedVoteTier = tier;
  updateVoteButtonState();
  // Envia imediatamente o voto ao servidor (comportamento antigo)
  if (roomCode) {
    socket.emit("vote", {code: roomCode, tier: tier});
  }
}

function updateVoteButtonState() {
  document.querySelectorAll(".tier-row").forEach(row => {
    row.classList.toggle("selected", row.dataset.tier === selectedVoteTier);
  });
}


function updateScoreSidebar(room) {
  const el = document.getElementById('scoreList');
  if (!el) return;
  if (!room || !room.players) {
    el.innerHTML = 'Nenhuma pontuação';
    return;
  }
  el.innerHTML = room.players.map(p => `<div style="display:flex;justify-content:space-between;padding:6px 0;"><span>👤 ${escapeHtml(p.name)}</span><b>${p.score || 0}</b></div>`).join('');
  // also render previews if present
  if (room.previews) renderPreviewsFromRoom(room.previews);
}

socket.on("vote_update", data => {
  const area = document.getElementById("tier-" + data.tier);
  if (!area) return;

  if (data.preview) {
    // preview element id
    let oldPreview = document.getElementById("voter-preview-" + CSS.escape(data.player_id));
    if (oldPreview) oldPreview.remove();

    const el = document.createElement("span");
    el.className = "voter preview";
    el.id = "voter-preview-" + data.player_id;
    el.textContent = "👤 " + data.player;
    area.appendChild(el);
  } else {
    // confirmed vote; remove any preview and add confirmed element
    let oldPreview = document.getElementById("voter-preview-" + CSS.escape(data.player_id));
    if (oldPreview) oldPreview.remove();

    let old = document.getElementById("voter-" + CSS.escape(data.player_id));
    if (old) old.remove();

    const el = document.createElement("span");
    el.className = "voter";
    el.id = "voter-" + data.player_id;
    el.textContent = "👤 " + data.player;
    area.appendChild(el);
  }

  const vc = document.getElementById("voteCount");
  if (vc) vc.textContent = `${data.votes}/${data.total} votos`;
});

socket.on("round_result", data => {
  document.getElementById("resultAnswer").textContent = data.answer;
  document.getElementById("resultAuthor").textContent = data.author;
  document.getElementById("correctTier").textContent = data.correct;

  document.getElementById("resultPlayers").innerHTML =
    data.results.map(r =>
      `<div class="result-row ${r.correct ? "good" : ""}">
        <span>${escapeHtml(r.player)} → <b>${r.tier}</b></span>
        <span>${r.correct ? "+1" : "+0"}</span>
      </div>`
    ).join("");

  document.getElementById("resultScores").innerHTML =
    "<h3>Placar</h3>" + data.scores.map((s, i) =>
      `<div class="result-row"><span>${i+1}º ${escapeHtml(s.name)}</span><b>${s.score}</b></div>`
    ).join("");

  // The next turn is automatic after 10 seconds.
  const nextButton = document.getElementById("nextButton");
  nextButton.style.display = "none";

  let countdown = 10;
  let countdownEl = document.getElementById("countdown");
  if (!countdownEl) {
    countdownEl = document.createElement("p");
    countdownEl.id = "countdown";
    countdownEl.style.textAlign = "center";
    countdownEl.style.color = "#aaa";
    nextButton.parentNode.insertBefore(countdownEl, nextButton);
  }

  countdownEl.textContent = data.game_over
    ? `Fim da partida em ${countdown}s...`
    : `Próximo turno em ${countdown}s...`;

  clearInterval(window.resultCountdown);
  window.resultCountdown = setInterval(() => {
    countdown--;
    countdownEl.textContent = data.game_over
      ? `Fim da partida em ${countdown}s...`
      : `Próximo turno em ${countdown}s...`;

    if (countdown <= 0) {
      clearInterval(window.resultCountdown);
      if (isHost) {
        socket.emit("auto_next_turn", {code: roomCode});
      }
    }
  }, 1000);

  show("result");
});

socket.on("game_finished", data => {
  document.getElementById("finalScores").innerHTML = data.scores.map((s, i) =>
    `<div class="result-row"><span>${i+1}º ${escapeHtml(s.name)}</span><b>${s.score} pontos</b></div>`
  ).join("");
  show("finished");
});

function submitTheme() {
  const raw = document.getElementById("themeInput").value.trim();
  if (!raw) return error("Digite pelo menos um tema.");

  const themes = raw
    .split(/[\n,]+/)
    .map(t => t.trim())
    .filter(Boolean)
    .slice(0, 3);

  if (themes.length === 0) return error("Digite pelo menos um tema.");

  socket.emit("submit_theme", {code: roomCode, theme: themes.join(",")});
  document.getElementById("themeInput").disabled = true;
  document.querySelector("#theme button").disabled = true;
}

function requestReturnToLobby() {
  if (!roomCode) return;
  socket.emit("request_return_to_lobby", {code: roomCode});
}

function voteReturnToLobby(choice) {
  if (!roomCode) return;
  socket.emit("vote_return_to_lobby", {code: roomCode, choice});
  hideReturnLobbyModal();
}

// ---- Lobby games rendering (host selection model) ----
window.lastSelectedGame = null;

function hostSelectGame(id) {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  if (!isHost) return error('Apenas o anfitrião pode escolher o jogo.');
  // marca o jogo selecionado (servidor emitirá game_selected)
  socket.emit('host_select_game', {code: roomCode, game: id});
}

// hostStartGame não utilizado quando o jogo inicia automaticamente ao selecionar; mantido por compatibilidade
function hostStartGame() {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  if (!isHost) return error('Apenas o anfitrião pode iniciar o jogo.');
  console.log('hostStartGame: emitting host_start_game for room', roomCode);
  socket.emit('host_start_game', {code: roomCode});
  // disable the start button briefly to avoid double clicks
  setTimeout(() => {
    const btn = document.querySelector('#startControl button, #startControl button');
    if (btn) btn.disabled = true;
  }, 50);
}

function renderLobbyGames(room) {
  const container = document.getElementById('lobbyGames');
  if (!container) return;
  const catalog = window.GAME_CATALOG || {};
  const selected = window.lastSelectedGame;

  const items = Object.keys(catalog).map(id => {
    const name = catalog[id] || id;
    const isSelected = selected === id;

    const clickable = isHost ? `onclick="hostSelectGame('${id}')"` : '';
    const classes = ['lobby-game-item'];
    if (isHost) classes.push('clickable');
    if (isSelected) classes.push('selected');

    let iconHtml = '';
    if (id === 'adedonha') {
      iconHtml = '<div class="game-icon">📝</div>';
    } else if (id === 'impostor') {
      iconHtml = '<div class="game-icon">👾</div>';
    } else if (id === 'monopoly') {
      iconHtml = '<div class="game-icon">🧐</div>';
    } else if (id === 'tier_guess') {
      iconHtml = '<div class="game-icon">🎯</div>';
    } else {
      iconHtml = '<div class="game-icon">🎮</div>';
    }

    const tierExtra = id === 'tier_guess' ? `\n      <div class="tier-mini-box">\n        <div class="tier-cell tier-s">S</div>\n        <div class="tier-cell tier-a">A</div>\n        <div class="tier-cell tier-b">B</div>\n      </div>` : '';

    return `
      <div class="${classes.join(' ')}" ${clickable}>
        ${iconHtml}
        <div class="game-name">${escapeHtml(name)}</div>
        ${tierExtra}
        <div style="height:18px;margin-top:6px">
          ${isSelected ? '<span title="Escolhido pelo anfitrião" style="font-size:18px;">✋</span>' : ''}
        </div>
      </div>`;
  });

  container.innerHTML = '<div class="lobby-games-grid">' + items.join('') + '</div>';

  // Render start control box (se houver seleção)
  const startControl = document.getElementById('startControl');
  if (startControl) {
    const sel = window.lastSelectedGame;
    if (!sel) {
      startControl.innerHTML = '';
    } else {
      const started = !!(room && room.current_game === sel && room.started);
      const name = (window.GAME_CATALOG && window.GAME_CATALOG[sel]) || sel;
      if (started) {
        startControl.innerHTML = `<div class="start-control-box"><div class="start-card"><div class="started">INICIADO</div></div></div>`;
      } else if (isHost) {
        startControl.innerHTML = `<div class="start-control-box"><div class="start-card"><button onclick="hostStartGame()">INICIAR</button></div></div>`;
      } else {
        // For non-hosts: do not show the selection text; only the hand under the selected box remains
        startControl.innerHTML = ``;
      }
    }
  }
}

socket.on('game_selected', data => {
  window.lastSelectedGame = data.game;
  if (window.currentRoom) {
    window.currentRoom.current_game = data.game;
    window.currentRoom.started = false;
  }
  renderLobbyGames(window.currentRoom);
});

socket.on('start_game', data => {
  // marca jogo como iniciado e troca para a tela do jogo correspondente
  if (window.currentRoom) {
    window.currentRoom.current_game = data.game;
    window.currentRoom.started = true;
  }
  window.lastStartedGame = data.game;
  renderLobbyGames(window.currentRoom);
  console.log('Iniciando jogo: ' + data.game);

  // Se o servidor não enviar o evento específico do jogo, ainda assim mudamos de tela
  if (data.game === 'monopoly') {
    show('monopoly');
  } else if (data.game === 'impostor') {
    show('impostor');
  } else if (data.game === 'adedonha') {
    show('adedonha');
  }
});

// Ensure lobby games render when receiving room update
// (append to existing room_update listener below)

function showReturnLobbyModal() {
  const modal = document.getElementById("returnLobbyModal");
  if (!modal) return;
  modal.classList.remove("hidden");
}

function hideReturnLobbyModal() {
  const modal = document.getElementById("returnLobbyModal");
  if (!modal) return;
  modal.classList.add("hidden");
}

socket.on("return_to_lobby_prompt", data => {
  showReturnLobbyModal();
});

socket.on("return_to_lobby_vote_status", data => {
  const modal = document.getElementById("returnLobbyModal");
  if (!modal) return;
  const title = modal.querySelector("h3");
  if (title) {
    title.textContent = `Voltar para o início? (${data.yes}/${data.total} votos sim)`;
  }
});

socket.on("return_to_lobby_result", data => {
  hideReturnLobbyModal();
  if (data.decision === "lobby") {
    show("lobby");
  } else if (data.decision === "theme") {
    show("theme");
  }
});

function submitAnswer() {
  const answer = document.getElementById("answerInput").value.trim();
  if (!answer) return error("Digite uma resposta.");
  socket.emit("submit_answer", {code: roomCode, answer});
}

function renderPreviewsFromRoom(previews) {
  // clear existing preview elements
  document.querySelectorAll('[id^="voter-preview-"]').forEach(e => e.remove());
  if (!previews) return;
  Object.entries(previews).forEach(([sid, tier]) => {
    const area = document.getElementById('tier-' + tier);
    if (!area) return;
    // find player name from currentRoom
    let name = sid;
    if (window.currentRoom && window.currentRoom.players) {
      const p = window.currentRoom.players.find(pl => pl.id === sid);
      if (p) name = p.name;
    }
    const el = document.createElement('span');
    el.className = 'voter preview';
    el.id = 'voter-preview-' + sid;
    el.textContent = '👤 ' + name;
    area.appendChild(el);
  });
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, m => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;"
  }[m]));
}

function startThemes() {
  socket.emit("start_themes", {code: roomCode});
}


socket.on("show_theme_screen", () => show("theme"));

// ---- Game voting handlers ----
function startGameVote() {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  socket.emit('start_game_vote', {code: roomCode});
  show('game_vote');
}

socket.on('show_game_vote', data => {
  const opts = data.options || [];
  const el = document.getElementById('gameOptions');
  el.innerHTML = opts.map(o => `
    <div class="game-option">
      <button onclick="submitGameVote('${o.id}')">Votar</button>
      <strong>${escapeHtml(o.name)}</strong>
    </div>
  `).join('');
  document.getElementById('gameVoteStatus').textContent = '';
  show('game_vote');
});

function submitGameVote(id) {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  socket.emit('submit_game_vote', {code: roomCode, game: id});
}

socket.on('game_vote_status', data => {
  const el = document.getElementById('gameVoteStatus');
  el.textContent = `Votos: ${data.voted}/${data.total}`;
});

socket.on('game_selected', data => {
  // mostra mensagem e espera start_game event(s)
  const msg = 'Jogo escolhido: ' + (data.name || data.game);
  // mostre brevemente e retorne ao lobby quando o jogo terminar (os handlers do jogo mostram as telas)
  console.log(msg);
});


// ---- Impostor handlers ----
socket.on('impostor_start', data => {
  console.log('received impostor_start', data);
  // Server sends only your_word; do not reveal or expect an is_impostor flag here.
  const word = data.your_word || '';
  // show word in large area
  const wEl = document.getElementById('impostorWord');
  if (wEl) wEl.textContent = word;

  document.getElementById('impostorInfo').textContent = '(Não revele sua palavra)';
  document.getElementById('impostorHint').value = '';
  // do NOT clear existing hints to maintain history
  // document.getElementById('impostorHints').innerHTML = '';
  const votesEl = document.getElementById('impostorVotes');
  if (votesEl) votesEl.innerHTML = '';
  show('impostor');
});

// Append single hint updates (chat-style)
socket.on('impostor_hint_update', data => {
  const el = document.getElementById('impostorHints');
  if (!el) return;
  const entry = document.createElement('div');
  entry.innerHTML = `<b>${escapeHtml(data.player)}</b>: ${escapeHtml(data.hint)}`;
  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;
});

// When full set of hints arrives, append them too (compat)
socket.on('impostor_hints', data => {
  const el = document.getElementById('impostorHints');
  if (!el) return;
  data.hints.forEach(h => {
    const entry = document.createElement('div');
    entry.innerHTML = `<b>${escapeHtml(h.player)}</b>: ${escapeHtml(h.hint)}`;
    el.appendChild(entry);
  });
  el.scrollTop = el.scrollHeight;
  // server will also emit impostor_show_voting; wait for that to render voting UI
});

socket.on('impostor_show_voting', data => {
  // data: {players: [{id,name}], threshold, total}
  const vEl = document.getElementById('impostorVotes');
  if (!vEl) return;
  vEl.innerHTML = '<div><b>Votação: quem é o impostor?</b></div>';
  vEl.innerHTML += '<div style="margin:6px 0;">' + data.players.map(p => `
    <button style="margin:2px;" onclick="impostorVote('${p.id}')">${escapeHtml(p.name)}</button>
  `).join('') + '</div>';
  vEl.innerHTML += `<div style="margin-top:6px;"><button onclick="impostorVote('skip')">Pular (skip)</button></div>`;
  vEl.innerHTML += `<div id="impostorVoteStatus" style="margin-top:8px;color:#555;">0/${data.total} votos — Eliminação automática com ${data.threshold} votos</div>`;
});

socket.on('impostor_vote_update', data => {
  const st = document.getElementById('impostorVoteStatus');
  if (!st) return;
  st.textContent = `${data.voted}/${data.total} votos`;
  // show counts per target if provided
  if (data.counts) {
    // convert counts object to readable list
    const parts = Object.keys(data.counts).map(k => `${escapeHtml(k)}: ${data.counts[k]}`);
    st.textContent += ' — ' + parts.join(', ');
  }
});

function submitImpostorHint() {
  const hint = document.getElementById('impostorHint').value.trim();
  if (!hint) return error('Escreva uma dica.');
  socket.emit('impostor_submit_hint', {code: roomCode, hint});
  document.getElementById('impostorHint').value = '';
}

socket.on('impostor_hints', data => {
  const el = document.getElementById('impostorHints');
  el.innerHTML = data.hints.map(h => `<div><b>${escapeHtml(h.player)}</b>: ${escapeHtml(h.hint)}</div>`).join('');
  // show voting UI
  const vEl = document.getElementById('impostorVotes');
  // build vote buttons
  socket.emit('request_room_players', {code: roomCode});
  // The server doesn't have a dedicated players list event; use room_update players to build vote buttons
});

// Build vote buttons when we receive a room update (players list exists there)
socket.on('room_update', room => {
  // existing room_update handler runs earlier; this listener augments the impostor vote UI if visible
  if (document.querySelector('#impostor').classList.contains('active')) {
    const vEl = document.getElementById('impostorVotes');
    vEl.innerHTML = room.players.map(p => `<button onclick="impostorVote('${p.id}')">Votar: ${escapeHtml(p.name)}</button>`).join('<br>');
  }
});

function impostorVote(targetId) {
  socket.emit('impostor_vote', {code: roomCode, target: targetId});
}

// ---- Adedonha handlers ----
socket.on('adedonha_start', data => {
  document.getElementById('adedonhaLetter').textContent = 'Letra: ' + data.letter;
  const cats = data.categories || [];
  const catsEl = document.getElementById('adedonhaCategories');
  catsEl.innerHTML = cats.map(c => `<span class="pill">${escapeHtml(c)}</span>`).join(' ');
  const inputs = document.getElementById('adedonhaInputs');
  inputs.innerHTML = cats.map(c => `<div><label>${escapeHtml(c)}: <input data-cat="${escapeHtml(c)}"></label></div>`).join('');
  document.getElementById('adedonhaResults').innerHTML = '';
  show('adedonha');
});

function submitAdedonha() {
  const inputs = Array.from(document.querySelectorAll('#adedonhaInputs input'));
  const answers = {};
  inputs.forEach(i => answers[i.dataset.cat] = i.value.trim());
  socket.emit('adedonha_submit', {code: roomCode, answers});
}

socket.on('adedonha_results', data => {
  const el = document.getElementById('adedonhaResults');
  // New payload format: { scores: {name: pts}, answers: {name: {cat: ans}} }
  if (data.scores && data.answers) {
    el.innerHTML = '<h3>Respostas</h3>' + Object.keys(data.answers).map(n => {
      const pairs = Object.keys(data.answers[n]).map(c => `${escapeHtml(c)}=${escapeHtml(data.answers[n][c] || '')}`);
      return `<div><b>${escapeHtml(n)}</b>: ${pairs.join(', ')}</div>`;
    }).join('');

    el.innerHTML += '<h3>Placar desta rodada</h3>' + Object.keys(data.scores).map(n => `<div>${escapeHtml(n)}: ${data.scores[n]} pontos</div>`).join('');

    // also show cumulative scores from currentRoom if available
    if (window.currentRoom) {
      el.innerHTML += '<h3>Placar acumulado (sala)</h3>' + window.currentRoom.players.map(p => `<div>${escapeHtml(p.name)}: ${p.score || 0} pts</div>`).join('');
    }
  } else if (data.results) {
    el.innerHTML = '<h3>Placar desta rodada</h3>' + Object.keys(data.results).map(n => `<div>${escapeHtml(n)}: ${data.results[n]} pontos</div>`).join('');
    if (window.currentRoom) {
      el.innerHTML += '<h3>Placar acumulado (sala)</h3>' + window.currentRoom.players.map(p => `<div>${escapeHtml(p.name)}: ${p.score || 0} pts</div>`).join('');
    }
  } else {
    el.innerHTML = '<p>Nenhum resultado.</p>';
  }
  setTimeout(() => show('lobby'), 7000);
});

// ---- Monopoly handlers (cliente) ----
socket.on('monopoly_start', data => {
  window.currentMonopoly = data;
  renderMonopolyState(data);
  show('monopoly');
});

socket.on('monopoly_state', data => {
  window.currentMonopoly = data;
  renderMonopolyState(data);
});

socket.on('monopoly_roll_result', data => {
  const last = document.getElementById('monopolyLast');
  if (!last) return;
  const spaceName = data.space && data.space.name ? data.space.name : '';
  last.textContent = `Dados: ${data.dice[0]} + ${data.dice[1]}. ${spaceName}${data.rent_paid ? ' — Pago aluguel: $' + data.rent_paid : ''}`;
});

function renderMonopolyState(m) {
  const msg = document.getElementById('monopolyMessage');
  if (msg) msg.textContent = m.message || '';

  const boardEl = document.getElementById('monopolyBoard');
  if (boardEl) {
    boardEl.innerHTML = m.board.map((s,i)=> {
      const ownerName = s.owner ? ' — ' + escapeHtml((m.players[s.owner]||{}).name || '') : '';
      const houses = s.houses ? ` casas:${s.houses}` : '';
      const hotel = s.hotel ? ' HOTEL' : '';
      return `<div class="mono-space" data-pos="${i}">${i}: ${escapeHtml(s.name)}${ownerName}${houses}${hotel}</div>`;
    }).join('');
  }

  const playersEl = document.getElementById('monopolyPlayers');
  if (playersEl) {
    playersEl.innerHTML = Object.values(m.players).map(p=> {
      const me = p.id === myId ? ' (Você)' : '';
      return `<div class="mono-player"><b>${escapeHtml(p.name)}${me}</b> — $${p.money} — pos: ${p.pos}` +
        (p.id === m.current_player ? ' <span style="color:green">← vez</span>' : '') +
        `</div>`;
    }).join('');
  }

  // Show build button if it's your turn and you're on a property you own
  const currentPlayer = m.players[m.current_player];
  const buildEl = document.getElementById('monopolyLast');
  if (buildEl) {
    buildEl.innerHTML = '';
    if (currentPlayer && currentPlayer.id === myId) {
      const pos = currentPlayer.pos;
      const space = m.board[pos];
      if (space && (space.type === 'property' || space.type === 'railroad') && space.owner === myId) {
        // show buy-build options
        buildEl.innerHTML = `Você está em ${escapeHtml(space.name)}. <button onclick="monopolyBuildHouse()">Construir casa/hotel</button>`;
      }
    }
  }
}

function monopolyRoll() {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  socket.emit('monopoly_roll', {code: roomCode});
}
function monopolyBuy() {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  socket.emit('monopoly_buy', {code: roomCode});
}
function monopolyBuildHouse() {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  socket.emit('monopoly_build_house', {code: roomCode});
}
function monopolyEndTurn() {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  socket.emit('monopoly_end_turn', {code: roomCode});
}

function startMonopolyDirect() {
  if (!roomCode) return error('Você precisa estar em uma sala.');
  socket.emit('start_game_vote', {code: roomCode, options: ['monopoly']});
}

