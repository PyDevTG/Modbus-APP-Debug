# Modbus TCP Client

Cliente **Modbus TCP** com interface gráfica moderna, feito em Python com [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) e [pyModbusTCP](https://github.com/sourceperl/pyModbusTCP). Pensado para quem trabalha com CLPs, inversores e medidores e precisa ler, escrever e monitorar registradores de forma rápida.

<!-- Adicione um print da tela em docs/screenshot.png e descomente a linha abaixo -->
<!-- ![Tela principal](docs/screenshot.png) -->

## Recursos

- Conexão por **IP, porta, Unit ID e timeout**, com indicador de status.
- Oito funções Modbus: **01, 02, 03, 04** (leitura) e **05, 06, 15, 16** (escrita).
- Leitura e escrita por botão, com valores em **decimal, hexadecimal (`0x`) e binário (`0b`)**.
- **Monitoramento cíclico** das leituras, com intervalo configurável (mínimo de 10 ms). Endereço, quantidade e intervalo podem ser alterados com o monitoramento rodando.
- **Escrita por duplo clique** em qualquer linha da tabela, inclusive durante o monitoramento.
- Tabela com valor **decimal, com sinal, hexadecimal e binário** de cada endereço.
- **Log** com horário de todas as operações e erros.
- Temas **Dark, Light e System**.
- A comunicação roda em threads separadas: a janela não trava se o dispositivo demorar a responder.

## Requisitos

- Windows 10 ou 11 / Linux

## Instalação 

-Faça download do arquivo executável ModbusClient.exe 
-Execute o arquivo 
-Siga os passos descritos no manual em pdf `Manual_Modbus_TCP_Client.pdf` para explorar todos os recursos.



### Uso rápido

1. Informe o **IP**, a **porta** (502 por padrão) e o **Unit ID**, e clique em **Conectar**.
2. Escolha a **função**, o **endereço inicial** e a **quantidade**.
3. Clique em **Ler** (ou **Escrever**, nas funções de escrita), ou em **Iniciar monitoramento** para ler ciclicamente.

Os endereços são **base 0**: o registrador 40001 da notação clássica corresponde ao endereço 0 da função 03.

## Funções suportadas

| Código | Função | Operação |
|:------:|--------|----------|
| 01 | Read Coils | Leitura |
| 02 | Read Discrete Inputs | Leitura |
| 03 | Read Holding Registers | Leitura |
| 04 | Read Input Registers | Leitura |
| 05 | Write Single Coil | Escrita |
| 06 | Write Single Register | Escrita |
| 15 | Write Multiple Coils | Escrita |
| 16 | Write Multiple Registers | Escrita |


## Documentação

O manual completo, com todas as opções detalhadas, está em [`Manual_Modbus_TCP_Client.pdf`](Manual_Modbus_TCP_Client.pdf).

## Estrutura do projeto

```
.
├── modbus_client_gui.py          # aplicativo
├── modbus_icon.ico               # ícone do aplicativo e do executável
├── ModbusClient.spec             # configuração do PyInstaller
├── requirements.txt              # dependências
└── Manual_Modbus_TCP_Client.pdf  # manual de utilização
```

## Licença

Defina a licença do projeto (por exemplo MIT) e adicione o arquivo `LICENSE` ao repositório.

---

Desenvolvido por Thiago dos Santos Alves, 2026.
