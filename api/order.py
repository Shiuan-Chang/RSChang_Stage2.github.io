from flask import Blueprint, request, jsonify
import pymysql
import jwt
import model.order
import requests
from dbutils.pooled_db import PooledDB
from common.utils.response import success, failure
from decouple import config
import json
import re
import datetime
import traceback

pool = PooledDB(
    creator=pymysql,
    maxconnections=10,
    blocking=True,
    ping=0,
    host='127.0.0.1',
    port=3306,
    user='root',
    password='Root!901',
    database='orderdb',
    charset='utf8',
)


order_blueprint = Blueprint('order', __name__)
SECRET_KEY = "your_hardcoded_secret_key"


@order_blueprint.route("/order/<order_number>", methods=["GET"])
def get_orderdb(order_number):
    try:
        result = model.order.get_order(order_number)
        if not result:
            return failure("沒有資料，請確認訂單編號", 400)

        # 處理 imgs_str
        if "imgs_str" not in result:
            return failure("警告: imgs_str 不存在於返回的結果中!", 400)

        try:
            imgs = json.loads(result["imgs_str"])
            if not isinstance(imgs, list) or not imgs:
                return failure("警告: imgs_str 不是一個非空列表!", 400)

            image_url = imgs[0]  # 假設已確定列表不為空
        except json.JSONDecodeError:
            return failure("錯誤: imgs_str 不是有效的 JSON 字符串!", 400)

        order_info = {
            "number": result["order_number"],
            "price": result["price"],
            "trip": {
                "attraction": {
                    "id": result["attraction_id"],
                    "name": result["attraction_name"],
                    "address": result["address"],
                    "image": json.loads(result["imgs_str"])[0]
                },
                "date": result["date"],
                "time": result["time_period"],
            },
            "contact": {
                "name": result["name"],
                "email": result["email"],
                "phone": result["phone"]
            },
            "status": result["status"]
        }
        return success(order_info)

    except Exception as e:
        print("出現錯誤:", str(e))
        print(traceback.format_exc())
        return failure(str(e), 500)


@order_blueprint.route("/orders", methods=["POST"])
def post_order():
    auth_header = request.headers.get('Authorization')

    if not auth_header or 'Bearer' not in auth_header:
        return jsonify({'error': 'Authorization header is missing or Bearer token is missing'}), 401

    userToken = auth_header.split(" ")[1]
    if not userToken:
        return jsonify({'error': '未登入系統，拒絕存取'}), 403
    data = request.get_json()
    try:
        decoded_token = jwt.decode(userToken, SECRET_KEY, algorithms=["HS256"])
        current_user = decoded_token['user_id']
        name = data["order"]["contact"]["name"]
        email = data["order"]["contact"]["email"]
        phone_number = data["order"]["contact"]["phone"]
        email_pattern = re.compile(
            "[a-zA-Z0-9.-_]{1,}@[a-zA-Z.-]{2,}[.]{1}[a-zA-Z]{2,}")
        phone_pattern = re.compile("^(09)[0-9]{8}$")
        if not all([name, email, phone_number]):
            return failure("訂單建立失敗，欄位不得為空", 400)
        elif not all([email_pattern.match(email), phone_pattern.match(phone_number)]):
            return failure("訂單建立失敗，電子郵件或電話格式不正確", 400)
        else:
            order_number = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
            payload = {
                "prime": data["prime"],
                "partner_key": config('partner_key'),
                "merchant_id": "rschang_CTBC",
                "details": "TapPay Test",
                "amount": data["order"]["price"],
                "order_number": order_number,
                "cardholder": {
                    "phone_number": phone_number,
                    "name": name,
                    "email": email
                },
                "remember": True
            }
            print(payload)
        headers = {'content-type': 'application/json',
                   "x-api-key": config('partner_key')}
        r = requests.post('https://sandbox.tappaysdk.com/tpc/payment/pay-by-prime',
                          data=json.dumps(payload), headers=headers)
        print(r.text)
        res = r.json()
        if res["status"] == 0:
            message = '付款成功'
        else:
            message = "付款失敗"
        result = model.order.post_order(
            current_user, order_number, data, res['status'])
        if result:
            return success({"number": order_number, "payment": {"status": res["status"], "message": message}})
    except Exception as e:
        print(e)
        return failure()
