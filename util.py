import os
from datetime import datetime
import xlsxwriter
import json

CONFIG_PATH = "./config"
links = {}
origins = {}
pools = {}
destinations = {}
blacklist = {}

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
    
def loadConfigFiles():
    global links, origins,pools, destinations, blacklist
    
    with open(os.path.join(CONFIG_PATH, "config.json"), 'r', encoding="utf-8") as f:
        links = json.load(f)
    
    with open(os.path.join(CONFIG_PATH, "origins.json"), 'r', encoding="utf-8") as f:
        origins = json.load(f)

    with open(os.path.join(CONFIG_PATH, "pools.json"), 'r', encoding="utf-8") as f:
        pools = json.load(f)
        pools = dict(map(lambda pool: (pool["poolIdentifier"], pool["poolName"]) ,pools))

    with open(os.path.join(CONFIG_PATH, "destinations.json"), 'r', encoding="utf-8") as f:
        tmpdestinations = json.load(f)
        destinations = {}
        for d in tmpdestinations:
            destinations[d["IATA"]] = {"name": d["name"], "country": d["country"]}
            
            
    with open(os.path.join(CONFIG_PATH, "blacklist.json"), 'r', encoding="utf-8") as f:
        blacklist = json.load(f)