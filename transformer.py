from lark import Lark, Transformer

class SimaiTransformer(Transformer):
    def title(self, n):
        n = n[0]
        return {"type": "title", "value": n.rstrip()}

    def artist(self, n):
        n = n[0]
        return {"type": "artist", "value": n.rstrip()}

    def smsg(self, n):
        pass

    def des(self, n):
        if len(n) == 2:
            num, des = n
            return {"type": "des", "value": (int(num), str(des))}
        else:
            return {"type": "des", "value": (-1, str(n[0]))}

    def freemsg(self, n):
        pass

    def first(self, n):
        return {"type": "wholebpm", "value": float(n[0])}

    def pvstart(self, n):
        pass

    def pvend(self, n):
        pass

    def wholebpm(self, n):
        return {"type": "wholebpm", "value": int(n[0])}

    def level(self, n):
        num, level = n
        return {"type": "level", "value": (int(num), level.rstrip())}

    def chart(self, n):
        num, raw_chart = n
        chart = ""
        for x in raw_chart.splitlines():
            if "||" not in x:
                chart += x

        chart = "".join(chart.split())
        return {"type": "chart", "value": (int(num), chart)}
        
    def amsg_first(self, n):
        pass

    def amsg_time(self, n):
        pass

    def amsg_content(self, n):
        pass

    def demo_seek(self, n):
        pass

    def demo_len(self, n):
        pass

    def chain(self, values):
        result = []
        for value in values:
            if isinstance(value, dict):
                result.append(value)

        return result