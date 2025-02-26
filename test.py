from fastapi.routing import APIRoute
from fastapi import FastAPI

app = FastAPI()

for route in app.routes:
    print(route.path, route.name)
