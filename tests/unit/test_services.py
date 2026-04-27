from video import is_rfdetr

def test_is_rfdetr():
    model_name = "RESNET"
    assert is_rfdetr(model_name) == False

