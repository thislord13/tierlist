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

http://localhost:5000

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
