"""
通用代理管理器
用于管理加载POC、安装nuclei、请求AI、更新APP等通用网络请求的代理设置
"""
import os
from typing import Optional, Dict

# 全局代理配置
_proxy_config = {
    'enabled': False,
    'type': 'http',
    'server': '',
    'username': '',
    'password': ''
}


def set_proxy_config(enabled: bool, proxy_type: str, server: str, username: str = '', password: str = ''):
    """
    设置全局代理配置
    
    参数:
        enabled: 是否启用代理
        proxy_type: 代理类型 (http, https, socks5)
        server: 代理服务器地址，如 127.0.0.1:7890
        username: 代理用户名（可选）
        password: 代理密码（可选）
    """
    global _proxy_config
    _proxy_config = {
        'enabled': enabled,
        'type': proxy_type,
        'server': server,
        'username': username,
        'password': password
    }
    
    # 设置环境变量，供底层库使用
    if enabled and server:
        proxy_url = _build_proxy_url()
        os.environ['http_proxy'] = proxy_url
        os.environ['https_proxy'] = proxy_url
        os.environ['all_proxy'] = proxy_url
    else:
        for key in ['http_proxy', 'https_proxy', 'all_proxy']:
            if key in os.environ:
                del os.environ[key]


def _build_proxy_url() -> str:
    """构建完整的代理URL"""
    if _proxy_config['username'] and _proxy_config['password']:
        return f"{_proxy_config['type']}://{_proxy_config['username']}:{_proxy_config['password']}@{_proxy_config['server']}"
    return f"{_proxy_config['type']}://{_proxy_config['server']}"


def get_proxy_url() -> Optional[str]:
    """获取完整的代理URL"""
    if _proxy_config['enabled'] and _proxy_config['server']:
        return _build_proxy_url()
    return None


def get_proxy_dict() -> Dict[str, str]:
    """获取requests库可用的代理字典"""
    proxy_url = get_proxy_url()
    if proxy_url:
        return {
            'http': proxy_url,
            'https': proxy_url
        }
    return {}


def get_proxy_config() -> dict:
    """获取当前代理配置"""
    return _proxy_config.copy()


def is_proxy_enabled() -> bool:
    """检查代理是否启用"""
    return _proxy_config['enabled'] and bool(_proxy_config['server'])
