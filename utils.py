import matplotlib.pyplot as plt

def plot_at_count(at_all_count: dict, at_person_count: dict):
    plt.bar([i + 1 for i in range(len(at_all_count))], at_all_count.values(), tick_label=at_all_count.keys(), width=0.4, color=['gray'], align='edge')
    plt.bar([i + 0.8 for i in range(len(at_all_count))], at_person_count.values(), width=0.4, color=['darkgray'])
    plt.legend(['@ALL', '@YOU'])
    plt.show()
    
a = {'a': 2, 'b': 4}
b = {'a': 5, 'b': 1}
plot_at_count(a, b)