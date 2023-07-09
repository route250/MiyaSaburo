
class StrList:
    def __init__(self):
        self._list = list()
        self._update = 0
        self._check = 0
    def clear(self):
        self._update += 1
        self._list.clear()
    def append(self,text : str):
        self._update += 1
        self._list.append(text)
    def is_update(self):
        return self._update != self._check
    def get_all(self,sep=""):
        self._check = self._update
        return sep.join(self._list)
    
def test():
    a = StrList()
    a.append("a")
    a.append("b")
    print( a.get_all(sep="@"))

if __name__ == '__main__':
    #main()
    test()
