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

import subprocess, time, datetime, os, re, csv, configparser, concurrent.futures

# Paramètres
TIMEOUT = 20

def save_csv_single(result):
    global isp
    fname = "./OUTPUT/"+initial_launch_datetime+"_"+isp+"_Single/"+initial_launch_datetime+"_"+isp+"_Single.csv"
    exists = False
    if os.path.exists(fname): exists = True
    file = open(fname, "a", newline='')
    try:
        writer = csv.writer(file)
        if exists == False:
            writer.writerow(("time","size","port","kbps","flag"))
        writer.writerow((result['datetime'],result['size'],result['port'],str(int(result['kbps'])),result['flag']))
    finally: file.close()

def save_csv_concurrent(result):
    global isp
    fname = "./OUTPUT/"+initial_launch_datetime+"_"+isp+"_Concurrent/"+initial_launch_datetime+"_"+isp+"_Concurrent.csv"
    exists = False
    if os.path.exists(fname): exists = True
    file = open(fname, "a", newline='')
    try:
        writer = csv.writer(file)
        if exists == False:
            writer.writerow(("time","size","port1","port2","kbps1","kbps2","flag"))
        writer.writerow((result['datetime'],result['size'],result['port1'],result['port2'],str(int(result['kbps1'])),str(int(result['kbps2'])),result['flag']))
    finally: file.close()

def launch_wget(port, size, type, date):
    global isp
    
    log_filename = "OUTPUT/"+initial_launch_datetime+"_"+isp+"_"+type+"/"+str(date)+"_Port"+str(port)+"_"+str(size)+"_"+isp+".log"

    if port == '80' or port == '81':
        protocol = "http"
    else:
        protocol = "https"

    url = protocol+"://bouygues.testdebit.info:"+port+"/"+size+"/"+size+".iso"

    cmd = subprocess.Popen('wget '+url+' -O /dev/null --report-speed=bits -v --timeout=3 --tries 1 -o '+log_filename, shell=True, stdout=subprocess.PIPE)
    
    i = 0
    while True:
        time.sleep(2)
        if i > TIMEOUT:
            raise Exception("wget_timeout")
        if cmd.poll() != None:
            # Si le port est fermé
            if cmd.poll() == 4:
                with open(log_filename, "r") as file:
                    line_result = re.sub("-{2}", "", file.readlines()[0]).split(" ")
                result = {}
                result['datetime'] = line_result[0]+"-"+line_result[1]
                result['size'] = size
                result['port'] = port
                result['kbps'] = -1
                result['log_filename'] = log_filename
                return(result)
            elif cmd.poll() != 0:
                raise Exception("wget_error")
            break;

    # Sinon, on continue car tout va bien
    with open(log_filename, "r") as file:
        line_result = re.sub("[()]", "", file.readlines()[-2]).split(" ")

    if line_result[3] == "Kb/s": multiplier = 1
    elif line_result[3] == "Mb/s": multiplier = 1000

    result = {}
    result['datetime'] = line_result[0]+"-"+line_result[1]
    result['size'] = size
    result['port'] = port
    result['kbps'] = float(line_result[2].replace(",", "."))*multiplier
    result['log_filename'] = log_filename

    return(result)

def launch_tcpdump(port, size, type, interface, date):
    global tcpdump_size
    pcap_filename = "OUTPUT/"+initial_launch_datetime+"_"+isp+"_"+type+"/"+str(date)+"_Port"+str(port)+"-"+str(size)+"_"+isp+".pcap"

    cmd = subprocess.Popen(['tcpdump', '-c', tcpdump_size, '-w', pcap_filename, "-i", interface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return [cmd, pcap_filename]

def is_anormal_single(rate):
    global normal_rate_kbps, threshold_single
    if float(rate)/float(normal_rate_kbps) < float(threshold_single):
        return True
    else: return False

def remaining_time_single(offset):
    global ports, size, normal_rate_kbps
    if size == "1M": size_ko = 1024
    elif size == "5M": size_ko = 1024*5
    elif size == "10M": size_ko = 1024*10
    elif size == "50M": size_ko = 1024*50
    elif size == "100M": size_ko = 1024*100
    elif size == "1G": size_ko = 1024*1000
    elif size == "10G": size_ko = 1024*10000
    s = int((len(ports)-offset)*size_ko*8/int(normal_rate_kbps) + (len(ports)-offset)*2)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return('{:d}:{:02d}:{:02d}'.format(h, m, s))

def remaining_time_concurrent(offset, nb_tests):
    global size, normal_rate_kbps
    if size == "1M": size_ko = 1024
    elif size == "5M": size_ko = 1024*5
    elif size == "10M": size_ko = 1024*10
    elif size == "50M": size_ko = 1024*50
    elif size == "100M": size_ko = 1024*100
    elif size == "1G": size_ko = 1024*1000
    elif size == "10G": size_ko = 1024*10000
    s = int((nb_tests-offset)*size_ko*8/int(normal_rate_kbps) + (nb_tests-offset)*3)*2
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
        time.sleep(1)
        try:
            date = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
            if tcpdump == "True":
                tcpdump_process = launch_tcpdump(port, size, "Single", interface, date)
            time.sleep(1)
            result = launch_wget(port, size, "Single", date)
            if tcpdump == "True":
                tcpdump_process[0].terminate()
            # Traitement des résultats
            # Si serveur injoignable
            if result['kbps'] == -1:
                print("\033[91mXX TCP "+port+" : 0 kbps ("+result['datetime']+") - ETA "+remaining_time_single(i)+" !! Serveur INJOIGNABLE (port bloqué ?) !!\033[0m", end='')
                result['flag'] = "UNREACHABLE"
                result['kbps'] = 0
            # Si le débit est OK, on supprime log et capture
            elif not is_anormal_single(result['kbps']):
                print("-- TCP "+port+" : "+str(int(result['kbps']))+" kbps ("+result['datetime']+") - ETA "+remaining_time_single(i), end='')
                result['flag'] = "pass"
                time.sleep(1)
                os.remove(result['log_filename'])
                if tcpdump == "True":
                    os.remove(tcpdump_process[1])
            # Si le débit est anormal, on conserve log et capture
            else: 
                print("?? TCP "+port+" : "+str(int(result['kbps']))+" kbps ("+result['datetime']+") - ETA "+remaining_time_single(i)+" !! Débit ANORMAL (1/2) !!")
                verification = launch_wget(port, size, "Single", date)
                # On vérifie une seconde fois si le débit est bien anormal. Si il l'est, on alerte et on garde capture+log
                if is_anormal_single(verification['kbps']):
                    result['flag'] = "ANORMAL_RATE"
                    print("\033[93m!! TCP "+port+" : "+str(int(verification['kbps']))+" kbps ("+verification['datetime']+") - ETA "+remaining_time_single(i)+" !! Débit ANORMAL (2/2) !!\033[0m", end='')
                # Sinon, on fait comme si il était correct dès le début
                else:
                    print("-- TCP "+port+" : "+str(int(verification['kbps']))+" kbps ("+verification['datetime']+") - ETA "+remaining_time_single(i), end='')
                    result['flag'] = "pass"
                    time.sleep(1)
                    os.remove(result['log_filename'])
                    if tcpdump == "True":
                        os.remove(tcpdump_process[1])
            print()
            i=i+1
            save_csv_single(result)
        except Exception as e:
            print(str(e))
            pass

def is_anormal_concurrent(delay, rate1, rate2):
    global threshold_concurrent_delay, threshold_concurrent_rate,normal_rate_kbps
    normal_rate_kbps = float(normal_rate_kbps)
    threshold_concurrent_rate = float(threshold_concurrent_rate)
    threshold_concurrent_delay = float(threshold_concurrent_delay)
    rate1 = int(rate1)
    rate2 = int(rate2)
    result = False
    if delay>threshold_concurrent_delay: result = True
    elif rate1>(normal_rate_kbps*threshold_concurrent_rate) or rate1<(normal_rate_kbps*(1-threshold_concurrent_rate)): result = True
    elif rate2>(normal_rate_kbps*threshold_concurrent_rate) or rate2<(normal_rate_kbps*(1-threshold_concurrent_rate)): result = True

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
                tcpdump_process = launch_tcpdump("s"+test[0]+"-"+test[1], size, "Concurrent", interface, date)
        time.sleep(0.8)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            first = executor.submit(launch_wget, test[0], size,"Concurrent", date)
            second = executor.submit(launch_wget, test[1], size,"Concurrent", date)
            i = 0
            tstamp = ""
            while not first.done() or not second.done():
                time.sleep(1)
                if first.done():
                    difference = 0
                    while not second.done():
                        time.sleep(1)
                        difference = difference +1
                    tstamp = second.result()['datetime']
                elif second.done():
                    difference = 0
                    while not first.done():
                        time.sleep(1)
                        difference = difference +1
                    tstamp = first.result()['datetime']
     
            time.sleep(1)
            if tcpdump == "True":
                tcpdump_process[0].terminate()
                time.sleep(1)
            message = ""
            color = "--"
            result['flag'] = "pass"

            # On fusionne les deux fichiers de logs
            data = data2 = "" 
            with open(first.result()['log_filename']) as fp: 
                data = fp.read() 
            with open(second.result()['log_filename']) as fp: 
                data2 = fp.read() 
            data += "\n\n"
            data += data2
            merged_logfile = "OUTPUT/"+initial_launch_datetime+"_"+isp+"_Concurrent/"+str(date)+"_Ports"+str(test[0])+"-"+str(test[1])+"_"+str(size)+"_"+isp+".log"
            with open (merged_logfile, 'a') as fp: 
                fp.write(data)
            os.remove(first.result()['log_filename'])
            os.remove(second.result()['log_filename'])


            rate1 = str(int(first.result()['kbps']))
            rate2 = str(int(second.result()['kbps']))

            if is_anormal_concurrent(difference, rate1, rate2):
                color = "??"
                message = "!! Débit ANORMAL (1/2) !!"

            if first.result()['kbps'] == -1 or second.result()['kbps'] == -1:
                if first.result()['kbps'] == -1: rate1 = str('0')
                else: rate1 = str(int(first.result()['kbps']))

                if second.result()['kbps'] == -1: rate2 = str('0')
                else: rate2 = str(int(second.result()['kbps']))

                color = "\033[91mXX"
                message = "!! Serveur INJOIGNABLE (port bloqué ?) !!"
                result['flag'] = "UNREACHABLE"

            if message == "":
                os.remove(merged_logfile)
                if tcpdump == "True":
                    os.remove(tcpdump_process[1])

            print(color+" TCP "+test[0]+" / TCP "+test[1]+" : "+rate1+" kbps / "+rate2+" kbps - Diff. "+str(difference)+" sec ("+tstamp+") - ETA : " +remaining_time_concurrent(j, len(tests))+" "+message+"\033[0m")
            j=j+1
            if is_anormal_concurrent(difference, rate1, rate2) and color == "??":
                first_verif = executor.submit(launch_wget, test[0], size,"Concurrent", date)
                second_verif = executor.submit(launch_wget, test[1], size,"Concurrent", date)

                i = 0
                tstamp = ""
                while not first_verif.done() or not second_verif.done():
                    time.sleep(0.5)
                    if first_verif.done():
                        difference_verif = 0
                        while not second_verif.done():
                            time.sleep(1)
                            difference_verif = difference_verif +1
                        tstamp = second_verif.result()['datetime']
                    elif second_verif.done():
                        difference_verif = 0
                        while not first_verif.done():
                            time.sleep(1)
                            difference_verif = difference_verif +1
                        tstamp = first_verif.result()['datetime']
        
                time.sleep(1)
                message = ""
                color = "--"

                rate1_verif = str(int(first_verif.result()['kbps']))
                rate2_verif = str(int(second_verif.result()['kbps']))

                if is_anormal_concurrent(difference_verif, rate1_verif, rate2_verif):
                    color = "\033[93m!!"
                    message = "!! Débit ANORMAL (2/2) !!"
                    result['flag'] = "ANORMAL_RATE"
                else:
                    os.remove(merged_logfile)
                    if tcpdump == "True":
                        os.remove(tcpdump_process[1])

                print(color+" TCP "+test[0]+" / TCP "+test[1]+" : "+rate1+" kbps / "+rate2+" kbps - Diff. "+str(difference)+" sec ("+tstamp+") - ETA : " +remaining_time_concurrent(j, len(test))+" "+message+"\033[0m")
        result['datetime'] = tstamp
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
        for i in range (1, 1024):
            ports.append((str(i)))
    elif config['auto_netneutra']['ports'] == "startend":
        ports_str = "de "+config['auto_netneutra']['start']+" à "+config['auto_netneutra']['end']
        for i in range (int(config['auto_netneutra']['start']), int(config['auto_netneutra']['end'])):
            ports.append((str(i)))
    elif config['auto_netneutra']['ports'] == "custom":
        ports = config['auto_netneutra']['custom_ports'].replace(" ","").split(",")
        ports_str = config['auto_netneutra']['custom_ports']
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
            ports_list_concurrent = config['auto_netneutra']['concurrent_ports'].replace(" ","").split(",")
            for port_list_concurrent in ports_list_concurrent:
                for i in range (0, len(ports)):
                    if port_list_concurrent != ports[i]:
                        tests.append([port_list_concurrent, ports[i]])
            print("-- Tous les ports vont être testés contre les suivants : "+config['auto_netneutra']['concurrent_ports'])
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
