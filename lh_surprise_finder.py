import requests
import copy
from datetime import datetime, date, timedelta
from dateutil.rrule import rrule, WEEKLY, FR
import asyncio
import aiohttp
import time
import util
from tqdm.asyncio import tqdm

async def flightSearch(content, session, index):
    #print(f"Request {req} sent")
    flight_data = await session.post("/jsonapi/availability", json=content)
    #print(content)
    #print(f"Request {req} finished")
    #print(f"{flight_data.status} Index: {index}")
    if flight_data.status == 200:
        #print(f"Request successfully {req} finished")
        return index
    return -1

async def timeSearch(content, session, index, hashList, pool, origin):

    flight_data = await session.post("/jsonapi/availability", json=content)
    destCode = pool["routes"][index]["destination"]

    if (flight_data.status == 200) and (util.destinations[destCode]["name"] not in util.blacklist):
        flight_data_json = await flight_data.json()
        destCode = pool["routes"][index]["destination"]
        obj_hash = hash(f'{origin["IATA"]}{destCode}{content["earliestOut"]}{content["latestRet"]}')
        
        flight = {
                    "origin": origin["name"],
                    "origin_IATA": origin["IATA"],
                    "destination": util.destinations[destCode]["name"],
                    "destination_IATA": destCode,
                    "departure": datetime.strptime(content["earliestOut"], "%Y-%m-%d"),
                    "arrival": datetime.strptime(content["latestRet"], "%Y-%m-%d"),
                    "price": flight_data_json["totalPrice"]["amount"],
                    "pool": util.pools[pool["poolIdentifier"]]
        }
        #print(f'{flight["origin"]} ({flight["origin_IATA"]}) -> {flight["destination"]} ({flight["destination_IATA"]})')
        return {"flight": flight, "hash": obj_hash}

def fetchPoolDestinations():
    sync_session = requests.Session()
    url = util.links["pool_url"]
    headers = util.links["pool_headers"]
    
    pool_data = sync_session.post(url, headers=headers, data={})
    
    sync_session.close()
    if pool_data.ok:
        print("Successfully fetched pool data")
        return pool_data.json()
    return []

def initPoolDestinations(pool):
    #Disable all destinations
    return list(map(lambda route: {"active": False, "value": route}, pool["routes"]))


def prepareFlightContent(origin, pool, minStay, maxStay, start, end, num_adults=1, num_childs=0, num_babies=0, days="", timeRestriction="", travelClass=""):
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
            
    
    for i in range(len(poolDestinations)):
      
        
        tmpPoolDestinations = copy.deepcopy(poolDestinations)
        tmpPoolDestinations[i]["active"] = True
        flight_content["poolDestinationsData"] = copy.deepcopy(tmpPoolDestinations)
        #print(tmpPoolDestinations)
        
                    
        tasks.append(
            asyncio.create_task(flightSearch(copy.deepcopy(flight_content), session, copy.deepcopy(i)))
        )
        
    availableDests = await tqdm.gather(*tasks)
    
    availableDests = [v for v in availableDests if v != -1]
    
    #print(availableDests)
    #availableDests = list(map(lambda t: t.result(),list(filter(lambda x: x.result() != -1, tasks))))
    
    availableDests.sort()
    
    return availableDests

async def getAvialableFlights(poolDestinations, availableDests, flight_content, searchDates, session, hashList, pool, origin):
    tasks = []
    foundFlights = []
    for index,dest in enumerate(poolDestinations):
                if index not in availableDests:
                    dest["active"]=True

    
    for i in availableDests:
        tmpPoolDestinations = copy.deepcopy(poolDestinations)
        tmpPoolDestinations[i]["active"] = True
        
        flight_content["poolDestinationsData"] = tmpPoolDestinations
        
                    
        for friday in searchDates:
            flight_content["earliestOut"] = friday.strftime("%Y-%m-%d")
            flight_content["latestRet"] = (friday + timedelta(days=3)).strftime("%Y-%m-%d")
                    
            tasks.append(
                asyncio.create_task(timeSearch(copy.deepcopy(flight_content), session,copy.deepcopy(i),hashList,pool,origin))
            )
                        
    flights = await tqdm.gather(*tasks)
    flights = [f for f in flights if f is not None]
    
    
    #flights = [i.result() for i in tasks if i.result() is not None]
    possible_flights = [i for i in flights if i["hash"] not in hashList]
    hashList = hashList + [f["hash"] for f in possible_flights]
    
            
    return [f["flight"] for f in possible_flights]
    

async def searchForFlights():
    start_date = date.today() + timedelta(days=2)
    end_date = date.today() + timedelta(days=50)
    searchDates = list(rrule(freq=WEEKLY, dtstart=start_date, until=end_date, byweekday=FR))
    
    pool_data = fetchPoolDestinations()
    if not pool_data:
        print("Error while fetching the pool destinations")
        exit(1)
        
    flight_url = util.links["flight_url"]
    headers = util.links["pool_headers"]
    
    foundFlights = []
    hash_list = []
    session = aiohttp.ClientSession(base_url=flight_url,headers=headers)
    
    print(f"Start-date: {start_date.strftime('%d.%m.%Y')}")
    print(f"End-date: {end_date.strftime('%d.%m.%Y')}")
    for origin in util.origins:
        print(f"Scanning flights for {origin['name']}")
        for pool in pool_data:
            
            #Pool doesnt match destinaion
            if pool["poolOrigin"] != origin["IATA"]:
                continue
            
            print(f"Scanning Pool {util.pools[pool['poolIdentifier']]}")
            poolDestinations = initPoolDestinations(pool)
           
            
            flight_Content = prepareFlightContent(pool["poolOrigin"], pool["poolIdentifier"],2,2,start_date,end_date, days="FRI_SUN")
    
            try:
        
                availableDests = await checkAvailableDestinations(poolDestinations,flight_Content,session)
            
                foundFlights = foundFlights + await getAvialableFlights(poolDestinations, availableDests,flight_Content,searchDates,session,hash_list,pool,origin)
            except KeyboardInterrupt:
                session.close()
    await session.close()
    return foundFlights


async def main():
    
    bm_start = time.perf_counter()
    
    util.loadConfigFiles()

    flights = await searchForFlights()
    

    util.writeToExcel(flights, "./results")
    
    bm_end = time.perf_counter()
    running_time = bm_end - bm_start
    
    print(f"Took {int(running_time/60)} Minutes and {int(running_time%60)} seconds")

asyncio.run(main())





