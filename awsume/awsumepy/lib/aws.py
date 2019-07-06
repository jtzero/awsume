import argparse
import dateutil
import boto3
import colorama
from datetime import datetime

try:
    import botostubs
except:
    pass

from . import profile as profile_lib
from . import cache as cache_lib
from . exceptions import RoleAuthenticationError, UserAuthenticationError
from . logger import logger
from . safe_print import safe_print


def parse_time(date_time: datetime):
    return date_time.astimezone(dateutil.tz.tzlocal()).strftime('%Y-%m-%d %H:%M:%S')


def assume_role(
    source_credentials: dict,
    role_arn: str,
    session_name: str,
    region: str = 'us-east-1',
    external_id: str = None,
    role_duration: int = None,
    mfa_serial: str = None,
    mfa_token: str = None,
) -> dict:
    logger.debug('Assuming role: {}'.format(role_arn))
    logger.debug('Session name: {}'.format(session_name))
    role_sts_client = boto3.session.Session(
        aws_access_key_id=source_credentials.get('AccessKeyId'),
        aws_secret_access_key=source_credentials.get('SecretAccessKey'),
        aws_session_token=source_credentials.get('SessionToken'),
        region_name=region,
    ).client('sts') # type: botostubs.STS

    try:
        kwargs = { 'RoleSessionName': session_name, 'RoleArn': role_arn }
        if external_id:
            kwargs['ExternalId'] = external_id
        if role_duration:
            kwargs['DurationSeconds'] = role_duration
        if mfa_serial:
            kwargs['SerialNumber'] = mfa_serial
            kwargs['TokenCode'] = mfa_token or profile_lib.get_mfa_token()
        role_session = role_sts_client.assume_role(**kwargs).get('Credentials')
        role_session['Expiration'] = role_session['Expiration'].astimezone(dateutil.tz.tzlocal())
        role_session['Region'] = region
    except Exception as e:
        raise RoleAuthenticationError(str(e))
    logger.debug('Role credentials received')
    safe_print(colorama.Fore.GREEN + 'Role credentials will expire {}'.format(parse_time(role_session['Expiration'])))
    return role_session


def get_session_token(source_credentials: dict, region: str = 'us-east-1', mfa_serial: str = None, mfa_token: str = None, ignore_cache: bool = False) -> dict:
    cache_file_name = 'aws-credentials-' + source_credentials.get('AccessKeyId')
    cache_session = cache_lib.read_aws_cache(cache_file_name)
    if cache_lib.valid_cache_session(cache_session) and not ignore_cache:
        logger.debug('Using cache session')
        safe_print(colorama.Fore.GREEN + 'Session token will expire at {}'.format(parse_time(cache_session['Expiration'])))
        return cache_session

    logger.debug('Getting session token')
    user_sts_client = boto3.session.Session(
        aws_access_key_id=source_credentials.get('AccessKeyId'),
        aws_secret_access_key=source_credentials.get('SecretAccessKey'),
        aws_session_token=source_credentials.get('SessionToken'),
        region_name=region,
    ).client('sts') # type: botostubs.STS
    try:
        user_session = user_sts_client.get_session_token(
            SerialNumber=mfa_serial if mfa_serial else None,
            TokenCode=None if not mfa_serial else (mfa_token or profile_lib.get_mfa_token()),
        ).get('Credentials')
        user_session['Expiration'] = user_session['Expiration'].astimezone(dateutil.tz.tzlocal())
        user_session['Region'] = region
    except Exception as e:
        raise UserAuthenticationError(str(e))
    logger.debug('Session token received')
    cache_lib.write_aws_cache(cache_file_name, user_session)
    if user_session.get('Expiration'):
        safe_print(colorama.Fore.GREEN + 'Session token will expire at {}'.format(parse_time(user_session['Expiration'])))
    return user_session


def get_account_id(credentials: dict):
    try:
        sts_client = boto3.session.Session(
            aws_access_key_id=credentials.get('AccessKeyId'),
            aws_secret_access_key=credentials.get('SecretAccessKey'),
            aws_session_token=credentials.get('SessionToken'),
            region_name=credentials.get('Region', 'us-east-1'),
        ).client('sts') # type: botostubs.STS
        response = sts_client.get_caller_identity()
        return response.get('Account', 'Unavailable')
    except:
        return 'Unavailable'
