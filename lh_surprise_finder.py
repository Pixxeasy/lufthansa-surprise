import json
import requests
import copy
from datetime import datetime, date, timedelta
from dateutil.rrule import rrule, WEEKLY, FR
import xlsxwriter
import asyncio
import aiohttp
import time
import os

def writeToExcel(items, path):
    if not os.path.exists(path):
        os.mkdir(path)
    current_time = datetime.now().strftime("%d_%m_%Y_%H_%M_%S") 
    workbook = xlsxwriter.Workbook(f"{path}/lh_surprise_{current_time}.xlsx")
    worksheet = workbook.add_worksheet()
    bold = workbook.add_format({"bold": 1})

    date_format = workbook.add_format({"num_format": "dd.mm.yyyy"})
    money_format = workbook.add_format({"num_format": "#,##0.00 €"})
   
    worksheet.write("A1", "Origin",bold)
    worksheet.write("B1", "Origin IATA",bold)
    worksheet.write("C1", "Destination", bold)
    worksheet.write("D1", "Destination IATA", bold)
    worksheet.write("E1", "Departure", bold)
    worksheet.write("F1", "Arrival", bold)
    worksheet.write("G1", "Price", bold)
    worksheet.write("H1", "Pool", bold)

    row = 1
    col = 0

    for item in items:
        worksheet.write_string(row, col, item["origin"])
        worksheet.write_string(row, col+1, item["origin_IATA"])
        worksheet.write_string(row, col+2, item["destination"])
        worksheet.write_string(row, col+3, item["destination_IATA"])
        worksheet.write_datetime(row, col+4, item["departure"], date_format)
        worksheet.write_datetime(row, col+5, item["arrival"], date_format)
        worksheet.write_number(row, col+6, item["price"], money_format)
        worksheet.write_string(row, col+7, item["pool"])

        row+=1

    workbook.close()


async def flightSearch(content, session, index, req):
    #print(f"Request {req} sent")
    flight_data = await session.post("/jsonapi/availability", json=content)
    #print(f"Request {req} finished")
    #print(f"{flight_data.status} Index: {index}")
    if flight_data.status == 200:
        #print(f"Request successfully {req} finished")
        return index
    return -1

async def timeSearch(content, session, index, hashList, pool, origin, destinations, pools,blacklist):

    flight_data = await session.post("/jsonapi/availability", json=content)
    destCode = pool["routes"][index]["destination"]

    if (flight_data.status == 200) and (destinations[destCode]["name"] not in blacklist):
        flight_data_json = await flight_data.json()
        destCode = pool["routes"][index]["destination"]
        obj_hash = hash(f'{origin["IATA"]}{destCode}{content["earliestOut"]}{content["latestRet"]}')
        
        flight = {
                    "origin": origin["name"],
                    "origin_IATA": origin["IATA"],
                    "destination": destinations[destCode]["name"],
                    "destination_IATA": destCode,
                    "departure": datetime.strptime(content["earliestOut"], "%Y-%m-%d"),
                    "arrival": datetime.strptime(content["latestRet"], "%Y-%m-%d"),
                    "price": flight_data_json["totalPrice"]["amount"],
                    "pool": pools[pool["poolIdentifier"]]
        }
        print(f'{flight["origin"]} ({flight["origin_IATA"]}) -> {flight["destination"]} ({flight["destination_IATA"]})')
        return {"flight": flight, "hash": obj_hash}

def loadConfigFiles():
    
    with open('config.json', 'r', encoding="utf-8") as f:
        links = json.load(f)
    
    with open('origins.json', 'r', encoding="utf-8") as f:
        origins = json.load(f)

    with open('pools.json', 'r', encoding="utf-8") as f:
        pools = json.load(f)
        pools = dict(map(lambda pool: (pool["poolIdentifier"], pool["poolName"]) ,pools))

    with open('destinations.json', 'r', encoding="utf-8") as f:
        tmpdestinations = json.load(f)
        destinations = {}
        for d in tmpdestinations:
            destinations[d["IATA"]] = {"name": d["name"], "country": d["country"]}
            
            
    with open('blacklist.json', 'r', encoding="utf-8") as f:
        blacklist = json.load(f)
            
    return links,origins,pools,destinations, blacklist

def fetchPoolDestinations(url, headers):
    sync_session = requests.Session()
    pool_data = sync_session.post(url, headers=headers, data={})
    
    sync_session.close()
    if pool_data.ok:
        print("Successfully fetched pool data")
        return pool_data.json()
    return []

def initPoolDestinations(pool):
    #Disable all destinations
    return list(map(lambda route: {"active": False, "value": route}, pool["routes"]))


def prepareFlightContent(origin, pool, num_adults, num_childs, num_babies, minStay, maxStay, days, timeRestriction, travelClass, start, end):
    #Prepare the request to search for flights
    flight_content = {"origin": origin, "pool": pool}

    #Number of passengers
    flight_content["numAdt"] = num_adults
    flight_content["numChd"] = num_childs
    flight_content["numInf"] = num_babies

    #Minimum Days to Stay
    flight_content["minStay"] = minStay

    #Maximum Days to Stay
    flight_content["maxStay"] = maxStay

    #Whether to only use Weekends (optional), eligible values: FRI_SUN, SAT_MON, SAT_SUN
    flight_content["dayType"] = days

    #Whether to restrict the time when the flights will go, eligible values: NOTEARLY (not before 9 am), LATEFLIGHTS (only after 2 pm)
    flight_content["timeRestriction"] = timeRestriction

    #Travel Class, elgible values: ECONOMY, BUSINESS
    flight_content["travelClass"] = travelClass
    flight_content["isTravelingBusiness"] = True if travelClass == "BUSINESS" else False

            #Earliest Departure, format: YYYY-MM-DD
    flight_content["earliestOut"] = start.strftime("%Y-%m-%d")

    #Latest Arrival, format: YYYY-MM-DD
    flight_content["latestRet"] = end.strftime("%Y-%m-%d")
    flight_content["lang"] = "de"
    flight_content["p"] = "OPQ"
    flight_content["userToken"] = "39409"
    
    return flight_content

async def checkAvailableDestinations(poolDestinations,flight_content, session):
    tasks = []
    
    await asyncio.sleep(0.5)
            
    async with asyncio.TaskGroup() as tg:
        for i in range(len(poolDestinations)):
      
            tmpPoolDestinations = copy.deepcopy(poolDestinations)
            tmpPoolDestinations[i]["active"] = True
            flight_content["poolDestinationsData"] = copy.deepcopy(tmpPoolDestinations)
            #print(tmpPoolDestinations)
                    
            tasks.append(
                tg.create_task(flightSearch(copy.deepcopy(flight_content), session, copy.deepcopy(i), 0))
            )
                    
            await asyncio.sleep(1)
        
    availableDests = list(map(lambda t: t.result(),list(filter(lambda x: x.result() != -1, tasks))))
    
    availableDests.sort()
    
    return availableDests

async def getAvialableFlights(poolDestinations, availableDests, flight_content, searchDates, session, hashList, pool, origin, destinations, pools,blacklist):
    tasks = []
    foundFlights = []
    for index,dest in enumerate(poolDestinations):
                if index not in availableDests:
                    dest["active"]=True

    
    for i in availableDests:
        tmpPoolDestinations = copy.deepcopy(poolDestinations)
        tmpPoolDestinations[i]["active"] = True
        
        flight_content["poolDestinationsData"] = tmpPoolDestinations
        async with asyncio.TaskGroup() as tg:
                    
            for friday in searchDates:
                flight_content["earliestOut"] = friday.strftime("%Y-%m-%d")
                flight_content["latestRet"] = (friday + timedelta(days=3)).strftime("%Y-%m-%d")
                    
                tasks.append(
                    tg.create_task(timeSearch(copy.deepcopy(flight_content), session,copy.deepcopy(i),hashList,pool,origin,destinations, pools,blacklist))
                )
                        
    await asyncio.sleep(1)
    
    flights = [i.result() for i in tasks if i.result() is not None]
    possible_flights = [i for i in flights if i["hash"] not in hashList]
    hashList = hashList + list(map(lambda x: x["hash"], possible_flights))
            
    return list(map(lambda f: f["flight"], possible_flights))
    

async def searchForFlights(flight_url, headers, origins, pool_data, destinations, pools,blacklist):
    start_date = date.today() + timedelta(days=2)
    end_date = date.today() + timedelta(days=50)
    searchDates = list(rrule(freq=WEEKLY, dtstart=start_date, until=end_date, byweekday=FR))
    
    foundFlights = []
    hash_list = []
    session = aiohttp.ClientSession(base_url=flight_url,headers=headers)
    
    print(f"Start-date: {start_date.strftime('%d.%m.%Y')}")
    print(f"End-date: {end_date.strftime('%d.%m.%Y')}")
    for origin in origins:
        print(f"Scanning flights for {origin['name']}")
        for pool in pool_data:
            #Pool doesnt match destinaion
            if pool["poolOrigin"] != origin["IATA"]:
                continue
            
            print(f"Scanning Pool {pools[pool['poolIdentifier']]}")
            poolDestinations = initPoolDestinations(pool)
           
            
            flight_Content = prepareFlightContent(pool["poolOrigin"], pool["poolIdentifier"],1,0,0,2,2,"FRI_SUN","","",start_date,end_date)
    
            try:
        
                availableDests = await checkAvailableDestinations(poolDestinations,flight_Content,session)
            
                foundFlights = foundFlights + await getAvialableFlights(poolDestinations, availableDests,flight_Content,searchDates,session,hash_list,pool,origin, destinations,pools,blacklist)
            except KeyboardInterrupt:
                session.close()
    await session.close()
    return foundFlights


async def main():
    
    bm_start = time.perf_counter()
    
    links,origins, pools, destinations,blacklist = loadConfigFiles()

    #Fetch pool Destinations
    pool_data = fetchPoolDestinations(links["pool_url"], links["pool_headers"])
    if not pool_data:
        print("Error while fetching the pool destinations")
        exit(1)


    flights = await searchForFlights(links["flight_url"], links["pool_headers"], origins, pool_data, destinations,pools,blacklist)
    

    writeToExcel(flights, "./results")
    
    bm_end = time.perf_counter()
    running_time = bm_end - bm_start
    
    print(f"Took {int(running_time/60)} Minutes and {int(running_time%60)} seconds")

asyncio.run(main())





