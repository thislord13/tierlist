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

