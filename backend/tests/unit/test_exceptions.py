import pytest
from app.exceptions import SagaException, NotFoundError, ValidationError, UnauthorizedError, AIProviderError, ForbiddenError, ConflictError

def test_exceptions():
    exc = SagaException("Base error", 500)
    assert exc.status_code == 500
    assert exc.message == "Base error"
    
    exc2 = NotFoundError("Entity")
    assert exc2.status_code == 404
    assert "Entity" in str(exc2)
    
    exc3 = ValidationError("Invalid input")
    assert exc3.status_code == 422
    assert "Invalid input" in str(exc3)
    
    exc4 = UnauthorizedError("Unauth")
    assert exc4.status_code == 401
    assert "Unauth" in str(exc4)
    
    exc5 = AIProviderError("OpenAI", "Rate limit")
    assert exc5.status_code == 502
    assert "Rate limit" in str(exc5)
    
    exc6 = ForbiddenError()
    assert exc6.status_code == 403
    
    exc7 = ConflictError()
    assert exc7.status_code == 409
