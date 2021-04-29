# MBGNN

For Beibei dataset, use
```
python .\labcode.py --data beibei --keepRate 0.4 --reg 1e-1
```

For Tmall dataset, run
```
python .\labcode.py --data tmall --reg 1 --save_path tmall --test_epoch 1
```

For Tianchi dataset, run
```
python .\labcode_preSamp.py --data tianchi --graphSampleN 40000 --reg 5e-2
```
