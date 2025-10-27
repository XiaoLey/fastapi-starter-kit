from fastapi import FastAPI

from app.support.modules_helper import execute_function_in_all_modules


def register(app: FastAPI):
    execute_function_in_all_modules('app.http.middleware', 'register', app)
