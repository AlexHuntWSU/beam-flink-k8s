import requests

job = 'e581e973a601cb86693791c3b152d564'
url = f'http://localhost:8081/v1/jobs/050d48c6b821c7f5c05bb72ab87ca39f/savepoints/483c11d0853a6766b529f7df2d0d2a5d'

response = requests.get(url)
print(response.text)