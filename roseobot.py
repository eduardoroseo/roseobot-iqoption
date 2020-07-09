import configparser
import json
import time
import threading
import requests
from datetime import datetime

from dateutil import tz

from iqoptionapi.stable_api import IQ_Option


def conta_config():
    arquivo = configparser.RawConfigParser()
    arquivo.read('config.txt')

    return {'email': arquivo.get('CREDENCIAIS', 'email'), 'senha': arquivo.get('CREDENCIAIS', 'senha')}


conta_config = conta_config()
sinais_usados = []

print('Conectando sua conta ...')
API = IQ_Option(conta_config['email'], conta_config['senha'])
API.connect()
print('Servidor conectado! Configurando banca')
API.change_balance('PRACTICE')  # PRACTICE / REAL
print('Banca configurada')
retry_connect = 0

while True:
    if not API.check_connect():
        print('Erro ao se conectar')
    else:
        print('Conectado com sucesso')
        time.sleep(0.5)
        retry_connect = 0
        break

    retry_connect = retry_connect + 1
    print('tentando reconectar [' + str(retry_connect) + ']')

    if retry_connect >= 5:
        break

    time.sleep(1)


def perfil():
    return json.loads(json.dumps(API.get_profile_ansyc()))


def timestamp_converter(time):  # Função para converter timestamp
    hora = datetime.strptime(datetime.utcfromtimestamp(time).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S')
    hora = hora.replace(tzinfo=tz.gettz('GMT'))

    return str(hora.astimezone(tz.gettz('America/Fortaleza')))[:-6]


def get_payout(par, tipo, timeframe=1):
    if tipo == 'turbo':
        a = API.get_all_profit()
        return int(100 * a[par]['turbo'])

    elif tipo == 'digital':

        API.subscribe_strike_list(par, timeframe)
        while True:
            d = API.get_digital_current_profit(par, timeframe)
            if d != False:
                d = int(d)
                break
            time.sleep(1)
        API.unsubscribe_strike_list(par, timeframe)
        return d


def configuracao():
    arquivo = configparser.RawConfigParser()
    arquivo.read('config.txt')

    return {'paridade': arquivo.get('GERAL', 'paridade'), 'valor_entrada': arquivo.get('GERAL', 'entrada'),
            'timeframe': arquivo.get('GERAL', 'timeframe')}


def carregar_sinais():
    arquivo = open('sinais.txt', encoding='UTF-8')
    lista = arquivo.read()
    arquivo.close()

    lista = lista.split('\n')
    for index, a in enumerate(lista):
        if a == '':
            del lista[index]

    return lista


def entrada(valor, par_moedas, acao_entrada, expiracao, hora_operacao, gale):
    status, id_order = API.buy(valor, par_moedas, acao_entrada, expiracao)
    if status:
        status, valor = API.check_win_v4(id_order)

        if status == 'win':
            icon = '✅😎 '
            status_do_pokas = 'Win!!'
        else:
            if valor == 0:
                icon = '❌👀 '
                status_do_pokas = 'Empatou!!'
            else:
                icon = '❌😖 '
                status_do_pokas = 'Loss!!'

        if acao_entrada == 'call':
            icon_acao = '📈 CALL'
        else:
            icon_acao = '📉 PUT'

        if status == 'loose' and gale > 0:
            payout = get_payout(par_moedas, 'turbo') / 100
            novo_valor = martingale('simples', valor, payout, valor + (valor * payout))
            threading.Thread(
                target=notificar_wpp,
                args=(
                    '👀 📊 *MARTINGALE* ' + str(gale) + ': ' + par_moedas + ' | ' + acao_entrada.upper() +
                    '\n*Novo Valor de entrada*: ' + str(novo_valor),)).start()
            gale = gale - 1
            threading.Thread(
                target=entrada,
                args=(
                    novo_valor,
                    par_moedas,
                    acao_entrada,
                    expiracao,
                    timestamp_converter(API.get_server_timestamp()),
                    gale,)).start()
            return True

        resultado = icon + status_do_pokas + ' ( ' + str(round(valor, 2)) + ' ) \n'
        sinal_formatado = icon_acao + ' | ' + par_moedas + ' | ' + hora_operacao + '\n'

        notificar_wpp(
            '-------------------------------------------- \n' +
            '*Resultado operação:* \n' +
            sinal_formatado +
            resultado +
            '--------------------------------------------'
        )

        return True
    else:
        print(str(status), str(valor))
        notificar_wpp("Operação NÃO EFETUADA: " + par_moedas)
        return False


def notificar_wpp(message):
    payload = {"to": "558588179596@c.us", "message": message}
    r = requests.get("http://localhost:3000", params=payload)
    return r.content


def martingale(tipo, valor, payout, perca):
    if tipo == 'simples':
        return valor * 2.2
    else:
        lucro_esperado = valor * payout
        while True:
            if round(valor * payout, 2) > round(abs(perca) + lucro_esperado, 2):
                return round(valor, 2)

            valor += 0.01


def operar_lista_de_sinais():
    print('carregando sinais ...')
    lista = carregar_sinais()
    print('sinais prontos! monitorando sinais. pressione CTRL + C para sair.')

    while True:
        # print(timestamp_converter(API.get_server_timestamp()))
        agora = timestamp_converter(API.get_server_timestamp())
        # agora = timestamp_converter(time.time())
        # print(agora)
        for sinal in lista:
            dados = sinal.split(',')
            if dados[0] == agora and sinal not in sinais_usados:
                sinais_usados.append(sinal)
                print(sinais_usados)
                valor_entrada = float(dados[4])
                par = dados[1]
                acao = dados[2].lower()
                expiracao = int(dados[3])
                gale = int(dados[5])

                threading.Thread(
                    target=notificar_wpp, args=(
                        '📊 FAZENDO ENTRADA: ' + par + ' | ' + '*' + acao.upper() + '*',)).start()
                threading.Thread(target=entrada, args=(valor_entrada, par, acao, expiracao, dados[0], gale,)).start()

        time.sleep(0.3)


operar_lista_de_sinais()
