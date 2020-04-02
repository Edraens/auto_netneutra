import os
import subprocess
import time
import threading
from selenium import webdriver

# Protocole à utiliser pour saturer l'uplink (TCP, UDP ou None pour désactiver l'uplink)
UPLINK_PROTOCOL = "UDP"
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
        args = "--max-time 15"
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
                if cmd.poll() == 28:
                    break
                elif cmd.poll() == 7:
                    raise Exception("curl_closed")
                elif cmd.poll() != 0:
                    raise Exception("curl_error")
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
# TODO
    cmd = os.popen(
        "curl -4 -o /dev/null -F 'filecontent=@/tmp/3000M_tmp.iso' http://bouygues.testdebit.info")

def stop_curl_uplink():
    cmd = os.popen(
        "killall curl")

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
        


def main():
    if UPLINK_PROTOCOL == "TCP":
        create_tmp_file()
        print("Launching continuous TCP upload...")
        curlUplinkThread = threading.Thread(target=launch_curl_uplink)
        curlUplinkThread.setDaemon(True)
        curlUplinkThread.start()
        time.sleep(2.5)
        print("")

    elif UPLINK_PROTOCOL == "UDP":
        print("Polling max uplink rate for 15 seconds...")
        maxrate_kbps = launch_curl_uplink(True)
        print("Launching continuous UDP upload at "+str(maxrate_kbps)+" kbps...")
        curlUplinkThread = threading.Thread(target=launch_iperf_uplink, args=(maxrate_kbps,))
        curlUplinkThread.setDaemon(True)
        curlUplinkThread.start()
        time.sleep(2.5)
        print("")

    # results = run_browsing_tests()
    # print("")
    # for url, result in results.items():
    #     print("Avg complete loading time for "+url+" : "+str(result)+" seconds")

    stop_curl_uplink()

main()
