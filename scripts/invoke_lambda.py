from __future__ import annotations

from json import dumps
from json import loads

from boto3 import client


def invoke_lambda(function_name, payload) -> str | None:
    """
    Invokes an AWS Lambda function with a given payload.

    :param function_name: The name of the Lambda function to invoke.
    :param payload: The payload to send to the Lambda function (dictionary).
    :return: The response from the Lambda function.
    """
    lambda_client = client("lambda")

    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=dumps(payload),
        )

        # Read and parse the response
        response_payload = response["Payload"].read()
        return loads(response_payload)

    except Exception as e:
        print(f"Error invoking Lambda function: {e}")
        return None


if __name__ == "__main__":
    lambda_function_name = "wknc-stats-update-lambda"

    response = invoke_lambda(function_name="wknc-stats-update-lambda", payload={})

    if response:
        print("Lambda response:", response)
