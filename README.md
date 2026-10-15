# TierGuess

Jogo multiplayer de Tier List para navegador.

## Tecnologias

- Python
- Flask
- Flask-SocketIO
- HTML/CSS/JavaScript
- Socket.IO

## Instalação

Crie um ambiente virtual:

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Linux:

```bash
source venv/bin/activate
```

Instale:

```bash
pip install -r requirements.txt
```

Execute:

```bash
python app.py
```

Abra:

http://127.0.0.1:5000

## Login com Discord

1. No [Discord Developer Portal](https://discord.com/developers/applications), crie uma aplicação e abra **OAuth2** para copiar o Client ID e gerar um Client Secret.
2. Em **OAuth2 > Redirects**, cadastre exatamente `http://127.0.0.1:5000/login/discord/callback` para desenvolvimento local.
3. Copie `.env.example` para `.env` e preencha `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` e `FLASK_SECRET_KEY`. Gere o segredo do Flask com `py -c "import secrets; print(secrets.token_hex(32))"`.
4. Instale as dependências com `pip install -r requirements.txt` e inicie normalmente com `start.bat`.

O usuário Discord é salvo em `instance/users.sqlite3`. A foto do Discord é usada inicialmente; após o login, clique em **Alterar foto** no cabeçalho para escolher uma imagem PNG, JPEG, WebP ou GIF de até 5 MB. O servidor valida e converte a imagem para WebP em `static/profile_uploads/`.

Se `FLASK_SECRET_KEY` não estiver definida, o app gera e mantém uma chave em `instance/flask_secret_key` para que as sessões de login continuem válidas após reiniciar o servidor. Em hospedagens com disco efêmero ou múltiplas instâncias, configure a mesma `FLASK_SECRET_KEY` persistente em todas elas.

Para publicar o site, configure a URL HTTPS pública em **OAuth2 > Redirects** e defina a mesma URL completa em `DISCORD_REDIRECT_URI` no `.env`. Nunca publique o arquivo `.env` nem compartilhe o Client Secret.

Para outras pessoas da mesma rede acessarem, use o IP do computador, por exemplo:

http://192.168.1.100:5000

## Jogo de mesa (Monopoli)

Para abrir a versão separada de Monopoli, execute:

```bash
python app2.py
```

Acesse http://localhost:5001 ou clique em **Jogar Monopoli** no menu do TierGuess. O arquivo `start.bat` inicia os dois jogos. O anfitrião cria uma sala e compartilha o código; cada pessoa abre o mesmo endereço no seu computador e entra com esse código. A sala aceita de 2 a 4 jogadores.

Na mesma rede, os outros computadores devem usar o IP do computador que iniciou o servidor, por exemplo `http://192.168.1.100:5001`. Para jogar pela internet, publique esse servidor em um endereço acessível pelos demais jogadores (por exemplo, com um túnel que encaminhe HTTP e WebSocket para a porta 5001).

## Observação

Esta é uma primeira versão funcional/protótipo. O próximo passo recomendado é adicionar:
- reconexão de jogadores;
- persistência das salas;
- botão de iniciar tema no servidor (em vez do atalho atual);
- limite configurável de rodadas;
- timer;
- animações;
- sons;
- ranking mais bonito;
- opção de nome da sala;
- modo público/privado;
- proteção contra spam;
- deploy com Gunicorn/eventlet/gevent ou servidor ASGI apropriado.


so baixe o python 3 baixe os requirements e inicie o .bat
