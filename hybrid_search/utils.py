

def chunks(lst, N):
    for idx in range(0, len(lst), N):
        yield lst[idx:idx+N]


