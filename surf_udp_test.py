import os
import subprocess
import time
import threading
import random
from selenium import webdriver

# Protocole à utiliser pour saturer l'uplink (TCP, UDP ou None pour désactiver l'uplink. ALL pour tester les 3)
UPLINK_PROTOCOL = "ALL"
# Nombre de tests à effectuer par site web
NB_OF_TESTS = 1

def create_tmp_file():
    if not os.path.exists("/tmp/3000M_tmp.iso"):
        print("Creating temporary file...")
        cmd = subprocess.Popen("dd if=/dev/urandom of=/tmp/3000M_tmp.iso bs=64000000 count=50",
                               shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while True:
            time.sleep(2)
            if cmd.poll() != None:
                break
        print("/tmp/3000M_tmp.iso created")
    else: print("Temporary file exists")

def launch_curl_uplink(probe=False):
    if probe:
        args = "--max-time 10"
        output = subprocess.PIPE
    else: 
        args = ""
        output = subprocess.STDOUT
    while True:
        cmd = subprocess.Popen(
            "curl -4 -o /dev/null -F 'filecontent=@/tmp/3000M_tmp.iso' http://bouygues.testdebit.info "+args, shell=True, stderr=output)
        while True:
            time.sleep(2)
            if cmd.poll() != None:
                if cmd.returncode == -15:
                    return
                break
        if probe:
            break
    raw_rate = cmd.communicate()[1].decode("utf-8").split("\n")[2].split("\r")[-1].split(" ")[-1]
    if "M" in raw_rate:
        rate = float(raw_rate.replace("M", ""))*8*1000
    elif "k" in raw_rate:
        rate = float(raw_rate.replace("k", ""))*8
    return rate

def launch_iperf_uplink(maxrate_kbps):
    i = 0
    while i < 30:
        port = random.randrange(9200, 9223)
        cmd = subprocess.Popen("iperf3 -4 -u -c paris.testdebit.info -p "+str(port)+" -b "+str(maxrate_kbps)+"k -t 5000 -i 5",
                               shell=True)

        time.sleep(2)
        if cmd.poll() == None:
            success = True
            print("iPerf launched")
            break
        else:
            print("Retrying other port...")

        i = i+1

def stop_curl_uplink():
    cmd = os.popen(
        "killall curl")


def stop_iperf_uplink():
    cmd = os.popen(
        "killall iperf3")

def run_browsing_tests():
    urls = [
        'impotsgouv',
        'mediapart',
        'microsoft',
        'wikipedia'
    ]

    results = {}

    for url in urls:
        full_url = 'http://tpr.testdebit.info/pageswebSTB/'+url
        sum_result = 0
        for i in range (0, NB_OF_TESTS):
            driver = webdriver.Chrome()
            driver.get(full_url)
            responseStart = driver.execute_script(
                "return window.performance.timing.responseStart")
            domComplete = driver.execute_script(
                "return window.performance.timing.domComplete")
            delay = domComplete - responseStart
            sum_result = sum_result + delay
            driver.quit()

        avg_webpage = round((sum_result/NB_OF_TESTS)/1000, 2)
        results.update({url: avg_webpage})

    return results
        


def launch_tests(ulproto):
    if ulproto == "TCP":
        print("Testing surf performance with TCP upload")
        create_tmp_file()
        print("Launching continuous TCP upload...")
        curlUplinkThread = threading.Thread(target=launch_curl_uplink)
        curlUplinkThread.setDaemon(True)
        curlUplinkThread.start()
        time.sleep(4)
        print("")

    elif ulproto == "UDP":
        print("Testing surf performance with UDP upload")
        print("Polling max uplink rate for 10 seconds...")
        maxrate_kbps = round(launch_curl_uplink(True)*1.25)
        print(maxrate_kbps)
        print("Launching continuous UDP upload at "+str(maxrate_kbps)+" kbps...")
        launch_iperf_uplink(maxrate_kbps)
        time.sleep(2.5)
        print("")
    else:
        print("Testing surf performance without uplink stress")

    results = run_browsing_tests()
    if ulproto == "TCP":
        stop_curl_uplink()
    elif ulproto == "UDP":
        stop_iperf_uplink()

    time.sleep(2)

    print("")
    print("")
    for url, result in results.items():
        displayresult.append("== Avg "+url+" ("+ulproto+" UL stress) : "+str(result)+" seconds")
    displayresult.append("")
    return displayresult

if __name__ == "__main__":
    displayresult = []
    if UPLINK_PROTOCOL == "ALL":
        launch_tests("None")
        print("")
        time.sleep(6)
        launch_tests("TCP")
        print("")
        time.sleep(6)
        launch_tests("UDP")
    else:
        launch_tests(UPLINK_PROTOCOL)

    for result in displayresult:
        print(result)
