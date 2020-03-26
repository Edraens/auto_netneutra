#!/usr/bin/env python3
# auto_netneutra : tests de neutralité des ports automatisé.
# Auteur : Pierre TINARD, février 2020

# En cas de problème de lancement de tcpdump par un utilisateur non-root :
"""
sudo groupadd pcap
sudo usermod -a -G pcap $USER
sudo chgrp pcap /usr/sbin/tcpdump
sudo setcap cap_net_raw,cap_net_admin=eip /usr/sbin/tcpdump
sudo ln -s /usr/sbin/tcpdump /usr/bin/tcpdump
"""

import subprocess
import time
import datetime
import os
import re
import csv
import configparser
import concurrent.futures
import random
import json

# Paramètres
DEBUG = False


def save_csv_single(result):
    global isp
    fname = "./OUTPUT/"+initial_launch_datetime+"_"+isp + \
        "_Single/"+initial_launch_datetime+"_"+isp+"_Single.csv"
    exists = False
    if os.path.exists(fname):
        exists = True
    file = open(fname, "a", newline='')
    try:
        writer = csv.writer(file)
        if exists == False:
            writer.writerow(("time", "size", "port", "kbps", "flag"))
        writer.writerow((result['datetime'], result['size'], result['port'], str(
            int(result['kbps'])), result['flag']))
    finally:
        file.close()


def save_csv_concurrent(result):
    global isp
    fname = "./OUTPUT/"+initial_launch_datetime+"_"+isp + \
        "_Concurrent/"+initial_launch_datetime+"_"+isp+"_Concurrent.csv"
    exists = False
    if os.path.exists(fname):
        exists = True
    file = open(fname, "a", newline='')
    try:
        writer = csv.writer(file)
        if exists == False:
            writer.writerow(("time", "size", "port1", "port2",
                             "kbps1", "kbps2", "flag"))
        writer.writerow((result['datetime'], result['size'], result['port1'], result['port2'], str(
            int(result['kbps1'])), str(int(result['kbps2'])), result['flag']))
    finally:
        file.close()


def launch_curl(port, size, type, date):
    log_filename = date
    if port == '80' or port == '81':
        protocol = "http"
    else:
        protocol = "https"

    url = protocol+'://paris.testdebit.info:' + port+'/'+size+'/'+size+'.iso'

    if DEBUG:
        args = ""
        print(url)
    else:
        args = "-s"

    cmd = subprocess.Popen('curl -4 -o /dev/null -w %{speed_download} '+url +
                           ' --connect-timeout 5 --max-time 12 '+args, shell=True, stdout=subprocess.PIPE)
    while True:
        time.sleep(2)
        if cmd.poll() != None:
            if DEBUG:
                print(cmd.poll())
            if cmd.poll() == 28:
                break
            elif cmd.poll() == 7:
                raise Exception("curl_closed")
            elif cmd.poll() != 0:
                raise Exception("curl_error")
            break

    rate = float(cmd.stdout.readline().decode("utf-8").replace(",", "."))*8
    return(rate)


def launch_iperf_udp(delay):
    global normal_rate_kbps
    bandwidth = str(int(normal_rate_kbps)+1000)+"k"
    bandwidth = "1300000k"
    while True:
        success = False
        port = random.randrange(9200, 9223)
        if DEBUG:
            print("iPerf sur port "+str(port))
            print("iperf3 -4 -u -c paris.testdebit.info -p "+str(port)+" -R -b "+bandwidth+" -t "+str(delay))
        cmd = subprocess.Popen("iperf3 -4 -u -c paris.testdebit.info -p "+str(port)+" -J -R -b "+bandwidth+" -t "+str(delay),
                               shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
        result = json.loads(cmd.communicate()[0])

        while True:
            time.sleep(2)
            if cmd.poll() != None:
                if DEBUG:
                    print(cmd.poll())
                if cmd.poll() == 0:
                    success = True
                break
        
        if success:
            sender_rate = result['end']['sum']['bits_per_second']
            lost_percentage = result['end']['sum']['lost_percent']/100

            rate = int(sender_rate*(1-lost_percentage)/1000)
            break

    return(rate)


def launch_tcpdump(port, size, type, interface, date):
    global tcpdump_size
    pcap_filename = "OUTPUT/"+initial_launch_datetime+"_"+isp+"_"+type + \
        "/"+str(date)+"_Port"+str(port)+"-"+str(size)+"_"+isp+".pcap"

    cmd = subprocess.Popen(['tcpdump', '-c', tcpdump_size, '-w', pcap_filename,
                            "-i", interface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return [cmd, pcap_filename]


def is_anormal_single(rate):
    global normal_rate_kbps, threshold_single
    if float(rate)/float(normal_rate_kbps) < float(threshold_single):
        return True
    else:
        return False


def remaining_time_single(offset):
    global ports, size, normal_rate_kbps
    if size == "1M":
        size_ko = 1024
    elif size == "5M":
        size_ko = 1024*5
    elif size == "10M":
        size_ko = 1024*10
    elif size == "50M":
        size_ko = 1024*50
    elif size == "100M":
        size_ko = 1024*100
    elif size == "1G":
        size_ko = 1024*1000
    elif size == "10G":
        size_ko = 1024*10000
    s = int((len(ports)-offset)*size_ko*8 /
            int(normal_rate_kbps) + (len(ports)-offset)*2)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return('{:d}:{:02d}:{:02d}'.format(h, m, s))


def remaining_time_concurrent(offset, nb_tests):
    global size, normal_rate_kbps
    if size == "1M":
        size_ko = 1024
    elif size == "5M":
        size_ko = 1024*5
    elif size == "10M":
        size_ko = 1024*10
    elif size == "50M":
        size_ko = 1024*50
    elif size == "100M":
        size_ko = 1024*100
    elif size == "1G":
        size_ko = 1024*1000
    elif size == "10G":
        size_ko = 1024*10000
    s = int((nb_tests-offset)*size_ko*8 /
            int(normal_rate_kbps) + (nb_tests-offset)*3)*2
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return('{:d}:{:02d}:{:02d}'.format(h, m, s))


def run_single_tests(ports, size):
    global interface, tcpdump
    if not os.path.exists("./OUTPUT"):
        os.mkdir("./OUTPUT")
    if not os.path.exists("./OUTPUT/"+initial_launch_datetime+"_"+isp+"_Single"):
        os.mkdir("./OUTPUT/"+initial_launch_datetime+"_"+isp+"_Single")

    i = 0
    for port in ports:
        result = {}
        time.sleep(1)
        date = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        if tcpdump == "True":
            tcpdump_process = launch_tcpdump(
                port, size, "Single", interface, date)
        time.sleep(1)

        if port != "UDP":
            try:
                status = "ok"
                resultrate = str(
                    int(launch_curl(port, size, "Single", date)/1024))
                if is_anormal_single(resultrate):
                    status = "low_rate"
            except Exception as e:
                resultrate = "0"
                if e.args[0] == "curl_closed":
                    status = "closed"
                pass
        else:
            try:
                status = "ok"
                resultrate = launch_iperf_udp(8)
                if is_anormal_single(resultrate):
                    status = "low_rate"
            except Exception as e:
                resultrate = "0"
                pass

        if tcpdump == "True":
            tcpdump_process[0].terminate()

        if status == "ok":
            if tcpdump == "True":
                os.remove(tcpdump_process[1])
            message = ""
            color = "--"
            result['flag'] = "pass"

        elif status == "closed":
            color = "\033[91mXX"
            message = "!! Serveur INJOIGNABLE (port bloqué ?) !!"
            result['flag'] = "UNREACHABLE"

        elif status == "low_rate":
            if port != "UDP":
                color = "!!"
                message = "!! Débit ANORMAL (1/2) !!"
                print(color+" Port "+port+" : "+f"{int(resultrate):_}"+" kbps - ETA : " +
                    remaining_time_single(i)+" "+message+"\033[0m")

                statusconfirm = "low_rate"
                try:
                    resultconfirm = str(
                        int(launch_curl(port, size, "Single", date)/1024))
                    if not is_anormal_single(resultconfirm):
                        statusconfirm = "ok"
                except Exception as e:
                    print(e.args)
                    pass

                if statusconfirm == "ok":
                    message = ""
                    color = "--"
                    result['flag'] = "pass"
                elif status == "low_rate":
                    color = "\033[93m!!"
                    message = "!! Débit ANORMAL (2/2) !!"
                    result['flag'] = "ANORMAL_RATE"
                resultrate = resultconfirm
            else:
                color = "\033[93m!!"
                message = "!! Test UDP (vérif. manuelle) !!"
                result['flag'] = "UDP"
        print(color+" Port "+port+" : "+f"{int(resultrate):_}"+" kbps - ETA : " +
              remaining_time_single(i)+" "+message+"\033[0m")

        result['datetime'] = date
        result['size'] = size
        result['port'] = port
        result['kbps'] = resultrate
        i = i+1
        save_csv_single(result)


def is_anormal_concurrent(delay, rate1, rate2):
    global threshold_concurrent_delay, threshold_concurrent_rate, normal_rate_kbps
    normal_rate_kbps = float(normal_rate_kbps)
    threshold_concurrent_rate = float(threshold_concurrent_rate)
    threshold_concurrent_delay = float(threshold_concurrent_delay)
    rate1 = int(rate1)
    rate2 = int(rate2)
    result = False
    if delay > threshold_concurrent_delay:
        result = True
    elif rate1 > (normal_rate_kbps*threshold_concurrent_rate) or rate1 < (normal_rate_kbps*(1-threshold_concurrent_rate)):
        result = True
    elif rate2 > (normal_rate_kbps*threshold_concurrent_rate) or rate2 < (normal_rate_kbps*(1-threshold_concurrent_rate)):
        result = True

    return result


def run_concurrent_tests(tests, size):
    global interface, tcpdump, isp, initial_launch_datetime
    if not os.path.exists("./OUTPUT"):
        os.mkdir("./OUTPUT")
    if not os.path.exists("./OUTPUT/"+initial_launch_datetime+"_"+isp+"_Concurrent"):
        os.mkdir("./OUTPUT/"+initial_launch_datetime+"_"+isp+"_Concurrent")

    j = 0
    for test in tests:
        result = {}
        date = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
        if tcpdump == "True":
            tcpdump_process = launch_tcpdump(
                "s"+test[0]+"-"+test[1], size, "Concurrent", interface, date)
        time.sleep(0.8)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            if test[0] != "UDP":
                first = executor.submit(
                    launch_curl, test[0], size, "Concurrent", date)
            else:
                first = executor.submit(launch_iperf_udp, 11)

            if test[1] != "UDP":
                second = executor.submit(
                    launch_curl, test[1], size, "Concurrent", date)
            else:
                second = executor.submit(launch_iperf_udp, 11)

            i = 0
            tstamp = ""
            while not first.done() or not second.done():
                time.sleep(1)
                if first.done():
                    difference = 0
                    while not second.done():
                        time.sleep(1)
                        difference = difference + 1
                elif second.done():
                    difference = 0
                    while not first.done():
                        time.sleep(1)
                        difference = difference + 1

            time.sleep(1)
            if tcpdump == "True":
                tcpdump_process[0].terminate()
                time.sleep(1)
            message = ""
            color = "--"
            result['flag'] = "pass"

            if test[0] != "UDP":
                rate1 = str(int(first.result()/1024))
            else:
                rate1 = str(int(first.result()))
            if test[1] != "UDP":
                rate2 = str(int(second.result()/1024))
            else:
                rate2 = str(int(second.result()))

            if is_anormal_concurrent(difference, rate1, rate2):
                color = "??"
                message = "!! Débit ANORMAL (1/2) !!"

            if first.result() == -1 or second.result() == -1:
                if first.result() == -1:
                    rate1 = str('0')
                else:
                    rate1 = str(int(first.result()))

                if second.result() == -1:
                    rate2 = str('0')
                else:
                    rate2 = str(int(second.result()))

                color = "\033[91mXX"
                message = "!! Serveur INJOIGNABLE (port bloqué ?) !!"
                result['flag'] = "UNREACHABLE"

            if message == "":
                if tcpdump == "True":
                    os.remove(tcpdump_process[1])

            if (test[0] == "UDP" or test[1] == "UDP"):
                color = "\033[93m!!"
                message = "!! Test UDP (vérif. manuelle) !!"
                result['flag'] = "UDP"

            print(color+" Port "+test[0]+" / Port "+test[1]+" : "+f"{int(rate1):_}"+" kbps / "+f"{int(rate2):_}"+" kbps - Diff. "+str(
                difference)+" - ETA : " + remaining_time_concurrent(j, len(tests))+" "+message+"\033[0m")
            j = j+1
            if is_anormal_concurrent(difference, rate1, rate2) and color == "??" and not (test[0] == "UDP" or test[1] == "UDP"):
                first_verif = executor.submit(
                    launch_curl, test[0], size, "Concurrent", date)
                second_verif = executor.submit(
                    launch_curl, test[1], size, "Concurrent", date)

                i = 0
                tstamp = ""
                while not first_verif.done() or not second_verif.done():
                    time.sleep(0.5)
                    if first_verif.done():
                        difference_verif = 0
                        while not second_verif.done():
                            time.sleep(1)
                            difference_verif = difference_verif + 1
                    elif second_verif.done():
                        difference_verif = 0
                        while not first_verif.done():
                            time.sleep(1)
                            difference_verif = difference_verif + 1

                time.sleep(1)
                message = ""
                color = "--"

                rate1_verif = str(int(first_verif.result()/1024))
                rate2_verif = str(int(second_verif.result()/1024))

                if is_anormal_concurrent(difference_verif, rate1_verif, rate2_verif):
                    color = "\033[93m"
                    message = "!! Débit ANORMAL (2/2) !!"
                    result['flag'] = "ANORMAL_RATE"
                else:
                    if tcpdump == "True":
                        os.remove(tcpdump_process[1])

                print(color+" Port "+test[0]+" / Port "+test[1]+" : "+f"{int(rate1_verif):_}"+" kbps / "+f"{int(rate2_verif):._}"+" kbps - Diff. "+str(
                    difference_verif)+" - ETA : " + remaining_time_concurrent(j, len(test))+" "+message+"\033[0m")
        result['datetime'] = date
        result['size'] = size
        result['port1'] = test[0]
        result['port2'] = test[1]
        result['kbps1'] = rate1
        result['kbps2'] = rate2
        save_csv_concurrent(result)


def main():
    global normal_rate_kbps, isp, interface, tcpdump, size, ports, threshold_single, tcpdump_size, threshold_concurrent_delay, threshold_concurrent_rate
    config = configparser.ConfigParser()
    config.read('config.ini')
    isp = config['auto_netneutra']['isp']
    size = config['auto_netneutra']['size']
    tcpdump = config['auto_netneutra']['tcpdump']
    tcpdump_size = config['auto_netneutra']['tcpdump_size']
    interface = config['auto_netneutra']['interface']
    normal_rate_kbps = config['auto_netneutra']['normal_rate_kbps']
    threshold_single = config['auto_netneutra']['threshold_single']
    threshold_concurrent_delay = config['auto_netneutra']['threshold_concurrent_delay']
    threshold_concurrent_rate = config['auto_netneutra']['threshold_concurrent_rate']

    ports = []
    ports_str = ""

    if config['auto_netneutra']['ports'] == "wellknown":
        ports_str = "well-known, 1 à 1024"
        for i in range(1, 1024):
            ports.append((str(i)))
    elif config['auto_netneutra']['ports'] == "startend":
        ports_str = "de "+config['auto_netneutra']['start'] + \
            " à "+config['auto_netneutra']['end']
        for i in range(int(config['auto_netneutra']['start']), int(config['auto_netneutra']['end'])):
            ports.append((str(i)))
    elif config['auto_netneutra']['ports'] == "custom":
        ports = config['auto_netneutra']['custom_ports'].replace(
            " ", "").split(",")
        ports_str = config['auto_netneutra']['custom_ports']

    if config['auto_netneutra']['iperf_udp'] == "True":
        ports.append("UDP")
        ports_str = ports_str+" + iPerf UDP"
    else:
        print("!! Configuration des ports incorrecte")
        exit()

    print("\n---- Lancement de auto_netneutra...\n")
    print("-- FAI : "+isp)
    print("-- Ports à tester : "+ports_str)
    print("-- Taille des fichiers : "+size)
    print("-- Débit normal de la connexion (kbps) : "+normal_rate_kbps)
    if tcpdump == "True":
        print("-- Taille des captures (nombre de paquets) : "+tcpdump_size)
        print("-- Interface à capturer (tcpdump) : "+interface+"\n")
    else:
        print("-- Captures tcpdump désactivées\n")

    if config['auto_netneutra']['single_tests'] == "True":
        print("--- Tests de débit sans mise en concurrence...\n")
        run_single_tests(ports, size)
        print("\n--- Fin des tests de débit sans mise en concurrence\n")

    if config['auto_netneutra']['concurrent_tests'] != "False":
        print("--- Tests de débit avec mise en concurrence...")
        if config['auto_netneutra']['concurrent_tests'] == "combination":
            tests = []
            for i in range(0, len(ports)):
                first = ports[i]
                for i in range(i+1, len(ports)):
                    second = ports[i]
                    tests.append([first, second])
            print("-- Tous les ports vont être testés entre eux")
        elif config['auto_netneutra']['concurrent_tests'] == "list":
            tests = []
            ports_list_concurrent = config['auto_netneutra']['concurrent_ports'].replace(
                " ", "").split(",")
            for port_list_concurrent in ports_list_concurrent:
                for i in range(0, len(ports)):
                    if port_list_concurrent != ports[i]:
                        tests.append([port_list_concurrent, ports[i]])
            print("-- Tous les ports vont être testés contre les suivants : " +
                  config['auto_netneutra']['concurrent_ports'])
        else:
            print("!! Configuration des tests concurrents incorrecte")
            exit()

        print("-- Nombre de tests : "+str(len(tests))+"\n")
        run_concurrent_tests(tests, size)
        print("\n--- Fin des tests de débit avec mise en concurrence\n")

    print("---- Fin de auto_netneutra, retrouvez les résultats dans le dossier OUTPUT\n")


tcpdump = ""
ports = ""
isp = ""
interface = ""
normal_rate_kbps = 0
size = ""
threshold_single = ""
threshold_concurrent_delay = ""
threshold_concurrent_rate = ""
tcpdump_size = ""
initial_launch_datetime = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")

main()
