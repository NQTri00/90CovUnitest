import pytest
from agent.parsers.java_parser import JavaParser
from agent.parsers.python_parser import PythonParser

# --- Mock Java Code ---
MOCK_JAVA_CODE = """
package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import com.example.repo.UserRepository;
import com.example.model.User;

@Service
public class UserService {

    @Autowired
    private UserRepository userRepository;

    public User getUserById(Long id) throws UserNotFoundException {
        if (id == null) {
            throw new IllegalArgumentException("Id cannot be null");
        }
        User user = userRepository.findById(id).orElse(null);
        if (user == null) {
            throw new UserNotFoundException("User not found");
        }
        return user;
    }

    private void doNothing() {
        // empty method
    }
}
"""

# --- Mock Python Code ---
MOCK_PYTHON_CODE = """
from typing import Optional
from myapp.repos import UserRepository
from myapp.models import User

class UserService:
    def __init__(self, user_repo: UserRepository, cache_client: RedisCache):
        self.user_repo = user_repo
        self.cache = cache_client

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        if user_id is None:
            raise ValueError("ID cannot be None")
        
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found")
        return user
"""

def test_java_parser():
    result = JavaParser.parse_file("src/main/java/com/example/service/UserService.java", MOCK_JAVA_CODE)
    
    assert result is not None
    assert result["class_name"] == "UserService"
    assert result["package"] == "com.example.service"
    assert "@Service" in result["annotations"]
    
    # Verify fields (dependencies)
    dependencies = result["dependencies"]
    assert len(dependencies) == 1
    assert dependencies[0]["field_name"] == "userRepository"
    assert dependencies[0]["type"] == "UserRepository"
    assert dependencies[0]["category"] == "repository"
    assert dependencies[0]["mock_strategy"] == "MockBean"
    
    # Verify methods
    methods = result["methods"]
    # getUserById and doNothing
    assert len(methods) == 2
    
    get_user_method = next(m for m in methods if m["name"] == "getUserById")
    assert get_user_method["visibility"] == "public"
    assert get_user_method["return_type"] == "User"
    assert len(get_user_method["params"]) == 1
    assert get_user_method["params"][0]["name"] == "id"
    assert get_user_method["params"][0]["type"] == "Long"
    assert "UserNotFoundException" in get_user_method["throws"]
    assert get_user_method["complexity"] == 3  # 1 base + 2 if statements
    assert get_user_method["priority"] == "MEDIUM"

def test_python_parser():
    parser = PythonParser("myapp/services/user_service.py", MOCK_PYTHON_CODE)
    classes = parser.parse()
    
    assert len(classes) == 1
    result = classes[0]
    
    assert result["class_name"] == "UserService"
    
    # Verify dependencies (from __init__)
    dependencies = result["dependencies"]
    assert len(dependencies) == 2
    
    user_repo_dep = next(d for d in dependencies if d["field_name"] == "user_repo")
    assert user_repo_dep["type"] == "UserRepository"
    assert user_repo_dep["category"] == "repository"
    
    cache_dep = next(d for d in dependencies if d["field_name"] == "cache_client")
    assert cache_dep["type"] == "RedisCache"
    assert cache_dep["category"] == "cache"

    # Verify methods (excluding __init__)
    methods = result["methods"]
    assert len(methods) == 1
    assert methods[0]["name"] == "get_user_by_id"
    assert methods[0]["visibility"] == "public"
    assert methods[0]["return_type"] == "Optional[User]"
    assert len(methods[0]["params"]) == 1
    assert methods[0]["params"][0]["name"] == "user_id"
    assert methods[0]["params"][0]["type"] == "int"
    assert "ValueError" in methods[0]["throws"]
    assert "UserNotFoundError" in methods[0]["throws"]
    assert methods[0]["complexity"] == 3  # 1 base + 2 ifs
