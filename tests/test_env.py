import sys

def test_python_version():
    assert sys.version_info >= (3, 10)

def test_imports():
    # Verify core packages can be imported successfully
    import langgraph
    import pydantic
    import javalang
    import docker
    import redis
    import celery
    import yaml
    
    assert langgraph is not None
    assert pydantic is not None
    assert javalang is not None
    assert docker is not None
    assert redis is not None
    assert celery is not None
    assert yaml is not None
