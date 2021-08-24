#!/usr/bin/python3

############################
# HDS - Hotspot Discord Status
# https://github.com/co8/hds
# ------------------
# co8.com 
# enrique r grullon
# e@co8.com
# discord: co8#1934 
############################

########
# Set Crontab
# crontab -e
# run script every minute. log to file
# */1 * * * * cd ~/hds; python3 hds.py  >> cron.log 2>&1
# @reboot cd ~/hds; python3 hds.py  >> cron.log 2>&1
# 0 0 1 * *  rm cron.log
# clear log file once a month at 0hr day 01
#
# 0 0 1 * * cd ~/hds; mv -i cron.log /logs/"cron_$(date '+%Y%m%d').log" 
# monthly, move and rename cron.log
#
# - run at reboot for dedicated device, eg: RasPi Zero W
###
# install DiscordWebhook module
# % pip3 install discordwebhook
########

#######
# Command Line Arguments
# REPORT
# python3 hds.py report - send miner report
# RESET
# python3 hds.py reset - set last.send to 0
#######

####import libs
from io import UnsupportedOperation
import sys
#from os import stat
from time import time
import requests
import json
from datetime import datetime
from discord_webhook import DiscordWebhook

### vars
### FINE TUNE #####
## override default values in config.json
wellness_check_hours = 8 #Default 8 hours. send status msg if X hours have lapsed since last message sent. slows miner, don't abuse
report_interval_hours = 72 #HOURS scheduled miner report. time after last report sent. slows miner, don't abuse
####
pop_status_minutes = 7 #MINUTES remove status msg when sending activity if activity is recent to last activity sent. keep discord tidy
##############
helium_api_endpoint = "https://api.helium.io/v1/"
config_file = "config.json"
activities = []
output_message = []
activity_history = []
hs = {}
wellness_check = history_repeats = wellness_check_seconds = report_interval_seconds = 0
interval_pop_status_seconds = int(60 * pop_status_minutes) 
send = send_report = add_welcome = send_wellness_check = False
invalidReasonShortNames = {
    'witness_too_close' : 'Too Close',
    'witness_rssi_too_high' : 'RSSI Too High',
    'witness_rssi_below_lower_bound' : 'RSSI BLB'
}
rewardShortNames = {
    'poc_witnesses' : 'Witness',
    'poc_challengees' : 'Beacon',
    'poc_challengers' : 'Challenger',
    'data_credits' : 'Data'
}


#### functions

def localBobcatMinerReport():
    #only run if bobcat_local_endpoint is set
    if 'bobcat_local_endpoint' in config and bool(config['bobcat_local_endpoint']):
    
        global send_report, output_message, report_interval_hours

        #send if next.report has been met
        if 'report' in config['next'] and hs['now'] > config['next']['report']:
            send_report = True
            print(f"\n{hs['time']} Bobcat Miner Report, every {report_interval_hours}hrs")

        if bool(send_report):
        #if 'bobcat_local_endpoint' in config and bool(config['bobcat_local_endpoint']) and bool(send_report):

            #try to get json or return error
            try:
                #LIVE local data
                bobcat_miner_json = config['bobcat_local_endpoint'] +"miner.json"
                bobcat_request = requests.get(bobcat_miner_json)
                data = bobcat_request.json()

                ### Dev only
                ###LOCAL load miner.json
                #with open("miner.json") as json_data_file:
                #    data = json.load(json_data_file)

            except ValueError:  #includes simplejson.decoder.JSONDecodeError
                print(f"\n{hs['time']} Bobcat Miner Local API failure")
                quit()

            temp_alert = '👍 ' if data['temp_alert'] == 'normal' else str.capitalize(data['temp_alert'])
            miner_state = '✅ + 🏃‍♂️' if data['miner']['State'] == 'running' else str.capitalize(data['miner']['State'])
            
            block_height = str.split(data['height'][0])
            block_height = "{:,}".format(int(block_height[-1]))

            if 'block_height' not in config['last']['report']:
                config['last']['report']['block_height'] = ''
            ###add to config if new
            if block_height != config['last']['report']['block_height']:
                config['last']['report']['block_height'] = block_height
                block_height = f"**{block_height}**" 

            #helium OTA version
            ota_helium = data['miner']['Image']
            ota_helium = ota_helium.split("_")
            ota_helium = str(ota_helium[1])
            if 'ota_helium' not in config['last']['report']:
                config['last']['report']['ota_helium'] = ''
            if ota_helium != config['last']['report']['ota_helium']:
                config['last']['report']['ota_helium'] = ota_helium
                ota_helium = f"**{ota_helium}**" 

            ota_bobcat = data['ota_version']
            if 'ota_bobcat' not in config['last']['report']:
                config['last']['report']['ota_bobcat'] = ''
            if ota_bobcat != config['last']['report']['ota_bobcat']:
                config['last']['report']['ota_bobcat'] = ota_bobcat
                ota_bobcat = f"**{ota_bobcat}**" 
        
            
            report = f"🔩🔩  **MINERity Report : {hs['time']}**  🔩🔩\nStatus: {miner_state} Temp: {temp_alert} Height: 📦{block_height}\nFirmware: Helium {ota_helium} | Bobcat {ota_bobcat}"
            #report = f"**MINERity Report:** {hs['time']}\nStatus: {miner_state} Temp: {temp_alert} 📦: {block_height}\n**Firmware** HELIUM: {ota_helium} / BOBCAT: {data['ota_version']}"

            output_message.insert(1, report) #insert at position 1 after status_msg

            #config values. repeat every X hours
            config['next']['report'] = hs['now'] + report_interval_seconds
            config['next']['report_nice'] = niceDate(config['next']['report'])

            print(f"\n{hs['time']} bobcat miner report", end='')

###load config.json vars
def loadConfig():
    global config, send_report, activity_history, wellness_check_hours, report_interval_hours, wellness_check_seconds, report_interval_seconds
    with open(config_file) as json_data_file:
        config = json.load(json_data_file)
    
    #wellness_check_hours - default sets config, or uses config value
    if 'wellness_check_hours' in config: 
        wellness_check_hours = config['wellness_check_hours']
    else:
        config['wellness_check_hours'] = wellness_check_hours
    wellness_check_seconds = int(60 * 60 * wellness_check_hours)

    #report_interval_hours - default sets config, or uses config value
    if 'report_interval_hours' in config:
        report_interval_hours = config['report_interval_hours']  
    else:
        config['report_interval_hours'] = report_interval_hours
    report_interval_seconds = int(60 * 60 * report_interval_hours)

    #add structure for elements
    if not 'owner' in config:
        config['owner'] = ''
    if not 'cursor' in config:
        config['cursor'] = ''
    if not 'last' in config:
        config['last'] = {}
    if not 'next' in config:
        config['next'] = {}
    if 'report' not in config['last']:
        config['last']['report'] = {}
    

    #command line arguments
    #send report if argument
    send_report = True if 'report' in sys.argv else False
    
    #reset hds. only clear config last/next and activity_history.
    if 'reset' in sys.argv:
        config['last'] = config['next'] = {}
        config['cursor'] = ''
        updateConfig()
        activity_history = []
        updateActivityHistory()

def updateConfig():
    global config
    with open(config_file, "w") as outfile:
        json.dump(config, outfile)

def loadActivityHistory():
    global activity_history
    with open('activity_history.json') as json_data_file:
        activity_history = json.load(json_data_file)

def updateActivityHistory():
    global activity_history, hs

    if bool(activity_history):

        #trim history. remove first 15 (oldest) elements if over 50 elements
        if len(activity_history) > 50: 
            print(f"\n{hs['time']} trimming activity_history")
            del activity_history[:15] 
        
        # save history details to config
        if not 'activity_history' in config['last']:
            config['last']['activity_history'] = {}

        config['last']['activity_history'] = {
            'count' : len(activity_history),
            'last' : hs['now'],
            'last_nice' : niceDate(hs['now'])
        }

        #write file
        with open('activity_history.json', "w") as outfile:
            json.dump(activity_history, outfile)

def getTime():
    global hs
    ###Time functions
    now = datetime.now()
    hs['now'] = round(datetime.timestamp(now))
    hs['time'] = str(now.strftime("%H:%M %D"))

###functions
def niceDate(time):
    timestamp = datetime.fromtimestamp(time)
    return timestamp.strftime("%H:%M %d/%b").upper()

def niceHotspotName(name):
    return name.replace('-', ' ').upper()

def niceHotspotInitials(name):
    return "".join(item[0].upper() for item in name.split())

def niceHNTAmount(amt):
    niceNum = .00000001
    niceNumSmall = 100000000
    
    # up to 3 decimal payments
    amt_output = '{:.3f}'.format(amt*niceNum)
    
    # 8 decimal places for micropayments
    #if amt > 0 and amt < 100000 :
    if amt in range(0, 100000):
        amt_output = '{:.8f}'.format(amt / niceNumSmall).rstrip('0')
        amt_output = f"`{amt_output}`"
    return str(amt_output)

#invalid reason nice name, or raw reason if not in dict
def niceInvalidReason(ir):
    return invalidReasonShortNames[ir] if ir in invalidReasonShortNames else str(ir)
    #output = str(ir)
    #if ir in invalidReasonShortNames:
    #   output = invalidReasonShortNames[ir]
    #return output

###activity type name to short name    
def rewardShortName(reward_type):
    return rewardShortNames[reward_type] if reward_type in rewardShortNames else reward_type.upper()
    #output = reward_type.upper()
    #if reward_type in rewardShortNames:
    #    output = rewardShortNames[reward_type]  
    #return output

def loadActivityData():
    global activities, config, hs, wellness_check, send, send_report, send_wellness_check

    #try to get json or return error
    try:
        #LIVE API data
        activity_endpoint = helium_api_endpoint +"hotspots/"+ config['hotspot'] +'/activity/'
        activity_request = requests.get(activity_endpoint)
        data = activity_request.json() 

        ### DEV Only
        ###LOCAL load data.json
        #with open("data.json") as json_data_file:
        #  data = json.load(json_data_file)

    #except: #catch all errors
    except ValueError:  #includes simplejson.decoder.JSONDecodeError
        print(f"\n{hs['time']} Helium Activity API. Response Failure")
        quit()

    #quit if no data
    if not 'data' in data:
        print(f"\n{hs['time']} Helium Activity API. No 'data' key in Response")
        quit()
    
    #set wellness_check if last.send exists
    if 'last' in config and 'send' in config['last']:
        wellness_check = int(config['last']['send'] + wellness_check_seconds)

    #add/update cursor to config
    if not 'cursor' in config:
        config['cursor'] = ''
    if config['cursor'] != data['cursor']:
        config['cursor'] = data['cursor']


    #send if time lapse since last status met. send report too
    if hs['now'] >= wellness_check:
        print(f"\n{hs['time']} Wellness Check after {wellness_check_hours}hrs, No API Activity", end='')
        send = send_wellness_check = send_report = True
        
    #no data or send_report false
    elif not data['data'] and not bool(send_report):
        #print(f"{hs['time']} no activities")
        print('.',end='')
        quit()
   
    #set activities, set last.send, update config
    else:
        send = True
        activities = data['data']
        #print('\n',end='') #line break for cron.log

###activity type poc_receipts_v1
def poc_receipts_v1(activity):
    valid_text = '💩  Invalid'
    time = niceDate(activity['time'])

    witnesses = {}
    wit_count = 0
    if 'path' in activity and 'witnesses' in activity['path'][0]:
        witnesses = activity['path'][0]['witnesses']
        wit_count = len(witnesses)
    #pluralize Witness
    wit_plural = 'es' if wit_count != 1 else ''
    wit_text = f"{wit_count} Witness{wit_plural}"

    #challenge accepted
    if 'challenger' in activity and activity['challenger'] == config['hotspot']:
        output_message.append(f"🏁 ...Challenged Beaconer, {wit_text}  `{time}`")

    #beacon sent
    elif 'challengee' in activity['path'][0] and activity['path'][0]['challengee'] == config['hotspot']:
        valid_wit_count = 0
        
        #beacon sent plus witness count and valid count
        for wit in witnesses:
            if bool(wit['is_valid']):
                valid_wit_count = valid_wit_count +1
        msg = f"🌋 Sent Beacon, {wit_text}"
        if bool(wit_count):
            if valid_wit_count == len(witnesses):
                    valid_wit_count = "All"
            msg += f", {valid_wit_count} Valid"
        msg += f"  `{time}`"
        output_message.append(msg)
          

    #witnessed beacon plus valid or invalid and invalid reason
    elif bool(witnesses):
            vw = 0 #valid witnesses
            valid_witness = False
            for w in witnesses:

                #valid witness count among witnesses
                if 'is_valid' in w and bool(w['is_valid']):
                    vw = vw +1

                if w['gateway'] == config['hotspot']:
                    witness_info = ''
                    if bool(w['is_valid']):
                        valid_witness = True
                        valid_text = '🛸 Valid' #🤙
                        witness_info = f", 1 of {wit_count}"
                    elif 'invalid_reason' in w:
                        valid_text = '💩 Invalid'
                        witness_info = ', '+ niceInvalidReason(w['invalid_reason'])

                    #output_message.append(f"{valid_text} Witness{witness_info}  `{time}`")
            
            #add valid witness count among witnesses
            if bool(valid_witness) and vw >= 1:
                if vw == len(witnesses):
                    vw = "All"
                witness_info += f", {vw} Valid"

            output_message.append(f"{valid_text} Witness{witness_info}  `{time}`")

    #other
    else:
        output_message.append(f"🏁 poc_receipts_v1 - {activity.upper()}  `{time}`")

def loopActivities():
    global send_report, history_repeats

    if bool(activities): # and not bool(send_report):

        #load history
        loadActivityHistory()

        for activity in activities:

            #skip if activity is in history
            if (activity['hash'] in activity_history): # and not bool(send_report):
                history_repeats = history_repeats +1 
                continue #skip this element, continue for-loop

            #save activity hash if not found
            else:
                activity_history.append(activity['hash'])

            #activity time
            time = niceDate(activity['time'])
            
            #reward
            if activity['type'] == 'rewards_v2':
                for reward in activity['rewards']:
                    rew = rewardShortName(reward['type'])
                    amt = niceHNTAmount(reward['amount'])
                    output_message.append(f"🍪 Reward 🥓{amt}, {rew}  `{time}`")
            #transferred data
            elif activity['type'] == 'state_channel_close_v1':
                for summary in activity['state_channel']['summaries']:
                    packet_plural = 's' if summary['num_packets'] != 1 else ''
                    output_message.append(f"🚛 Transferred {summary['num_packets']} Packet{packet_plural} ({summary['num_dcs']} DC)  `{time}`")
            
            #...challenge accepted
            elif activity['type'] == 'poc_request_v1':
                output_message.append(f"🎲 Created Challenge...  `{time}`")

            #beacon sent, valid witness, invalid witness
            elif activity['type'] == 'poc_receipts_v1':
                poc_receipts_v1(activity)
            
            #other
            else:
                other_type = activity['type']
                output_message.append(f"🚀 Activity: {other_type.upper()}  `{time}`")
#loopActivities()  

def loadHotspotDataAndStatusMsg():
    ###hotspot data
    global hs, config, add_welcome
    new_balance = new_reward_scale = new_block_height = new_status = False

    #try to get json or return error
    try:
        hs_endpoint = helium_api_endpoint +"hotspots/"+ config['hotspot']
        hs_request = requests.get(hs_endpoint)
        data = hs_request.json()
        if not data['data']:
            print(f"no hotspot data {hs['time']}")
            quit()
        else:
            hotspot_data = data['data']
        del hs_request

    #except: #catch all errors
    except ValueError:  #includes simplejson.decoder.JSONDecodeError
        print(f"\n{hs['time']} Helium Hotspot API failure")
        quit()
    
    #quit if no data
    if not 'data' in data:
        print(f"\n{hs['time']} Helium Hotspot API. No 'data' key in Response")
        quit()

    ### hotspot data
    hs_add = {
        'owner' : hotspot_data['owner'],
        'name' : niceHotspotName(hotspot_data['name']),
        'status' : str(hotspot_data['status']['online']).upper(),
        'height' : hotspot_data['status']['height'],
        'block' : hotspot_data['block'],
        'reward_scale' : '{:.2f}'.format(round(hotspot_data['reward_scale'],2))
    }
    hs.update(hs_add)
    hs['initials'] = niceHotspotInitials(hs['name'])
    del data, hotspot_data

    #add/update cursor to config. supports hotspot ownership transfers
    if not 'owner' in config or config['owner'] != hs['owner']:
        config['owner'] = hs['owner']

    ###block height percentage
    hs['block_height'] = round(hs['height'] / hs['block'] * 100, 2)
    hs['block_height'] = "*NSYNC" if hs['block_height'] > 98 else str(hs['block_height']) +'%'
    
    if 'block_height' not in config['last']:
        config['last']['block_height'] = '0'
    ###add to config if new
    if hs['block_height'] != config['last']['block_height']:
        new_block_height = True
        config['last']['block_height'] = hs['block_height']

    ###wallet data
    wallet_request = requests.get(helium_api_endpoint +"accounts/"+ hs['owner'])
    w = wallet_request.json()
    hs['balance'] = niceHNTAmount(w['data']['balance'])
    if 'balance' not in config['last']:
        config['last']['balance'] = '0'
    ###add to config if new
    if hs['balance'] != config['last']['balance']:
        new_balance = True
        config['last']['balance'] = hs['balance']
    del wallet_request, w

    ### reward_scale
    if 'reward_scale' not in config['last']:
        config['last']['reward_scale'] = '0'
    ###add to config if new
    if hs['reward_scale'] != config['last']['reward_scale']:
        new_reward_scale = True
        config['last']['reward_scale'] = hs['reward_scale']
    
     ### status
    if 'status' not in config['last']:
        config['last']['status'] = ''
    ###add to config if new
    if hs['status'] != config['last']['status']:
        new_status = True
        config['last']['status'] = hs['status']
    
    #### STYLED status text
    ### bold balance if has changed
    balance_styled = '**'+ hs['balance'] +'**' if bool(new_balance) else hs['balance']
    ### bold reward_scale if has changed
    reward_scale_styled = '**'+ hs['reward_scale'] +'**' if bool(new_reward_scale) else hs['reward_scale']
    ### bold block_height if has changed
    block_height_styled = '**'+ hs['block_height'] +'**' if bool(new_block_height) else hs['block_height']
    ### bold status if not 'online'
    status_styled = '**'+ hs['status'] +'**' if bool(new_status) else hs['status']

    #default status msg
    status_msg = '📡 **'+ hs['initials'] +'** 🔥'+ status_styled +' 🥑'+ block_height_styled +' 🍕'+ reward_scale_styled +' 🥓'+ balance_styled
    
    #insert to top of output_message
    output_message.insert(0, status_msg)

    #add in lapse message
    if bool(send_wellness_check):
        lapse_msg = "`🚧 No Activities from API in the Last {wellness_check_hours} Hours.`"
        output_message.insert(0, lapse_msg)


def discordSend():
    global send, add_welcome, send_report

    #send if no last.send in config
    if 'last' in config and not 'send' in config['last']:
        send = add_welcome = True

    #send if more than 1 (default) msg
    elif len(output_message) > 1:
        send = True
    
    #unless send report, don't send, repeats only 
    elif not bool(send_report):
        send = False
        print(':',end='') #print(f"{hs['time']} repeat activities")
        quit()

    #add welcome msg to output if no config[last][send]
    if bool(add_welcome):
        output_message.insert(0, f"🤙 **{hs['name']}  [ 📡 {hs['initials']} ]**")
        print(f"\n{hs['time']} Welcome msg added", end='')

    if bool(send):
        #only send activity, remove status if recently sent. keep if report
        if 'last' in config and 'send' in config['last'] and hs['now'] < (config['last']['send'] + interval_pop_status_seconds):
            output_message.pop(0)

        #update last.send to be last status sent
        config['last']['send'] = hs['now']
        config['last']['send_nice'] = niceDate(config['last']['send'])

        discord_message = '\n'.join(output_message)
        
        ### Dev only
        #print(discord_message)
        #exit()

        webhook = DiscordWebhook(url=config['discord_webhook'], content=discord_message)
        ###send
        webhook_response = webhook.execute()
        return webhook_response.reason
    


#########################
### main
def main():
    getTime()
    loadConfig()
    loadActivityData()

    #if activity data...
    loadHotspotDataAndStatusMsg()  
    loopActivities()
    localBobcatMinerReport()
    discord_response_reason = discordSend()

    #update history
    updateActivityHistory()

    #update config
    updateConfig()

    #status log
    print(f"\n{hs['time']} act:{str(len(activities))} repeats:{str(history_repeats)} msgs:{str(len(output_message))} discord:{discord_response_reason}")


### execute main() if main is first module
if __name__ == '__main__':
    main()