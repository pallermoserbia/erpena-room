# Erpena uredjaj u sali (Raspberry Pi)

Servis koji se pokrece pri startu i sam se javlja Erpeni. Kad organizator u Erpeni pokrene snimanje sastanka u toj sali,
uredjaj otvara mikrofon i salje zvuk za transkript. Kad se snimanje zavrsi, mikrofon se zatvara.

- Veza je izlazna i sifrovana (HTTPS), ne otvaraju se portovi na mrezi sale.
- Kodek, bitrate i frekvencija se podesavaju u Erpeni (Sastanci > Podesavanja > Uredjaj u sali), uredjaj ih preuzima sam.
- Ako veza pukne, delovi cekaju na disku (do 500 MB) i salju se kad se veza vrati.
- Mikrofon radi samo za vreme snimanja koje je pokrenuo organizator, nikad sam od sebe.

Preporuka: Raspberry Pi 4 ili Zero 2 W, Raspberry Pi OS Lite, USB konferencijski mikrofon sa ugradjenim
poništavanjem jeke i usmeravanjem (npr. Jabra Speak2 75 ili ReSpeaker USB Mic Array). Pokreni `bash install.sh`.

## Instalacija i azuriranje sa GitHub-a
    sudo apt install -y git
    git clone https://github.com/VASA-ORGANIZACIJA/erpena-room.git
    cd erpena-room
    sudo bash install.sh

Azuriranje (uredjaj se sam restartuje ako je vec upariran):

    cd erpena-room
    git pull
    sudo bash install.sh

Uparivanje i podesavanje mikrofona vidi na kraju ispisa install.sh. Token uredjaja je samo na uredjaju (/etc/erpena-room), nikad u repozitorijumu.
