# Simple PLL Control for 10GHz Transverter

The application will load settings previously stored and enable the PLL on boot. 

If you connect via a serial connection, you will get a menu system that allows you to
* Reset config to defaults
* Toggle the PLL on/off. This does not persist.
* Change the IF frequency
* Change the RF (output frequency, after mixing)

To access the menu connect at 115200 8N1 to the serial port. On Linux this is `/dev/ttyACM0` by default.

```sh
minicom -b 115200 --device /dev/ttyACM0
```

## Deploying

You need to set up micropython on the PiPico. https://micropython.org/download/RPI_PICO/

You can use the UF2 bootloader (holding down the boot button during power up with USB) and copy the
downloaded image onto the Pico.

Then install `rshell` using your `pipx install rshell`

```sh
$ rshell -p /dev/ttyACM0
> rsync . /pyboard
```

Basically, copy the `main.py` and the contents of the `lib` onto the Pico.

You can run `repl` to get to the repl from with rshell, and press Ctl-D to
soft reset the Pico and enter the menu if you want to test.
