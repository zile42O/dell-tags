import requests
from bs4 import BeautifulSoup
import threading
from selenium import webdriver
from loguru import logger

maxThreads = 10
logger.add("worker.log", rotation="50 MB")
tags = open("tags.txt", "r").readlines()

useProxy = False # True or False
proxyUsername = ""
proxyPassword = ""
proxyHost = ""

proxyConfig = {
	"http": f"http://{proxyUsername}:{proxyPassword}@{proxyHost}",
	"https": f"https://{proxyUsername}:{proxyPassword}@{proxyHost}"
}

def getCookies(assetId = None):
	"""best option for capturing real browser based cookies, instead requests library."""

	logger.debug(f"Getting cookies..")
	edge_options = webdriver.EdgeOptions()
	edge_options.add_argument("--ignore-certificate-errors")
	edge_options.add_argument("--enable-chrome-browser-cloud-management")
	edge_options.add_argument('--no-sandbox')
	edge_options.add_argument('--disable-dev-shm-usage')
	edge_options.add_experimental_option('excludeSwitches', ['enable-logging'])
	driver = webdriver.Edge(options=edge_options)

	if assetId == None:
		driver.get("https://www.dell.com/support/home/en-us")
	else:
		driver.get(f"https://www.dell.com/support/product-details/en-us/servicetag/0-{assetId}/overview")

	cookies = driver.get_cookies()
	driver.close()
	cookiedict = {cookie['name']: cookie['value'] for cookie in cookies}
	cookie_string = "; ".join([f"{key}={value}" for key, value in cookiedict.items()])
	return cookie_string


def checkProxy(proxy):
	"""function for testing validty of proxy."""
	logger.debug("Checking proxy..")
	try:
		ip_response = requests.get("http://httpbin.org/ip", proxies=proxy)
		logger.success(f"Proxy is ok. IP Address: {ip_response.json()['origin']}")
	except Exception as e:
		logger.error(f"Proxy is bad. Error: {e}")

def checkTag(tag):
	"""function for processing the dell servicetag."""
	global useProxy
	global cookies

	# clean tag
	tag = tag.replace("\n", "")

	headers = {
		"Cookie": cookies,
		"Origin": "https://www.dell.com",
		"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
	}
	url = f"https://www.dell.com/support/components/detectproduct/encvalue/{tag}?appname=warranty"

	if useProxy:
		req = requests.get(url, headers=headers, proxies=proxyConfig)
	else:
		req = requests.get(url, headers=headers)

	assetId = req.text
	if req.status_code != 200:
		# recursion
		return checkTag(tag)
	try:
		headers = {
			"Content-Type": "application/json",
			"Cookie": cookies,
			"Origin": "https://www.dell.com",
			"Referer": f"https://www.dell.com/support/product-details/en-us/servicetag/0-{assetId}/overview",
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
		}
		payload = {
			"assetFormat": "ServiceTag",
			"assetId": assetId,
			"appName": "warranty",
			"loadScript": True,
			"useDds": True
		}
		url = "https://www.dell.com/support/contractservices/en-us/entitlement/details"

		if useProxy:
			info = requests.post(url, json=payload, headers=headers, proxies=proxyConfig)
		else:
			info = requests.post(url, json=payload, headers=headers)

		if info.status_code != 200:
			cookies = getCookies(assetId)
			headers["cookie"] = cookies
			if useProxy:
				info = requests.post(url, json=payload, headers=headers, proxies=proxyConfig)
			else:
				info = requests.post(url, json=payload, headers=headers)

		soup = BeautifulSoup(info.text, 'html.parser')

		table = soup.find('table', id='WarrantyCmsViewModel-table')
		productName = soup.find('div', class_='dds__flex-column dds__h4 dds__font-weight-normal dds__break-word desc-size text-gray-900') # path for product name

		if productName == None or productName == "":
			logger.error(f"[-] {tag}")
			return

		second_row = table.find_all('tr')[1]
		ship_date = second_row.find_all('td')[2].text.strip()
		productLocation = second_row.find_all('td')[3].text.strip()

		#logger.debug(f"tag: {tag} assetId: {assetId} ship_date: {ship_date} productLocation: {productLocation}")
		TextResult = f"{tag.strip()} | {ship_date.strip()} | {productName.text.strip()} | {productLocation.strip()}\n"
		TextResult = TextResult.encode('utf-8', 'ignore').decode('utf-8')

		with open("valid.txt", "a", encoding="utf-8") as output:
			output.write(TextResult)

		logger.success(f"[+] {tag}")
	except Exception as e:
		logger.error(f"[-] {tag} error: {e}")
		return

count = 0
if tags == 0:
	logger.error("No data in tags.txt")
else:
	logger.info("Starting Tag checker..")
	cookies = getCookies()
	if useProxy:
		checkProxy(proxyConfig)
	while count < len(tags):
		if threading.active_count() < maxThreads:
			threading.Thread(target=checkTag, args=(tags[count],)).start()
			count += 1

# by zile42O