# Views here.
import fileinput
from django.http import HttpResponse
from django.shortcuts import render,redirect
from portal.models import *
import django.utils.simplejson as json
from portal.forms import *
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
import logging
import random
import socket
from django.db.models import Q
from datetime import datetime
from django.utils import timezone
from calendar import monthrange
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from nuages.settings import LOGIN_REDIRECT_URL as baseurl


COBBLERPORT = 80

if os.path.exists("%s/portal/customtypes.py" % settings.PWD):
    from customtypes import *
    import customtypes


def getdefault():
    defaults = Default.objects.all()
    if not defaults:
        ip = socket.gethostbyname(socket.gethostname())
        default = Default(name='default',consoleip=ip)
        default.save()
    else:
        default = Default.objects.all()[0]
    return default

def getvspherecert(host):
    try:
        import ssl
        from M2Crypto import X509
    except:
        return None,None
    pem = ssl.get_server_certificate((host, 443))
    x509 = X509.load_cert_string(pem, X509.FORMAT_PEM)
    fp = x509.get_fingerprint('sha1')
    sha1 = ':'.join(fp[pos:pos+2] for pos in xrange(0, len(fp), 2))
    subject = x509.get_subject()
    return subject.CN, sha1

def checkconn(host,port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        return True
    except socket.error:
        return False


def checkstorage(numvms,virtualprovider,disksize1,disksize2,storagedomain):
    size = int(disksize1)
    if disksize2:
        size = size+float(disksize2)
    size = numvms*size
    if virtualprovider.type =='ovirt':
        ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
        storageinfo = ovirt.getstorage()
        ovirt.close()
        remaining = int(storageinfo[storagedomain][1]) - size
        if remaining <=0:
            return "Not enough space on storagedomain %s.%s GB needed !"  % (storagedomain,size)
        else:
            return 'OK'
    if virtualprovider.type =='kvirt':
        kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
        storageinfo = kvirt.getstorage()
        kvirt.close()
        remaining = int(storageinfo[storagedomain][1]) - size
        if remaining <=0:
            return "Not enough space on storagedomain %s.%s GB needed !"  % (storagedomain,size)
        else:
            return 'OK'
    elif virtualprovider.type == 'vsphere':
        jythoncommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s" % (settings.PWD, 'getstorage', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu )
        storageinfo = os.popen(jythoncommand).read()
        storageinfo= ast.literal_eval(storageinfo)
        remaining = int(storageinfo[storagedomain][1]) - size
        if remaining <=0:
            return "Not enough space on storagedomain %s.%s GB needed !"  % (storagedomain,size)
        else:
            return 'OK'
    elif virtualprovider.type =='vsphere2':
	vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
        storageinfo = vsphere.getstorage()
        vsphere.close()
        remaining = int(storageinfo[storagedomain][1]) - size
        if remaining <=0:
            return "Not enough space on storagedomain %s.%s GB needed !"  % (storagedomain,size)
        else:
            return 'OK'

def customlogin(request, *args, **kwargs):
    if request.method == "POST":
        keyboard = request.POST.get('keyboard')
        request.session['keyboard'] = keyboard
        request.session.modified = True
    return auth_views.login(request, *args, **kwargs)

@login_required
def create(request):
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    if request.method == 'POST':
        name              = request.POST.get('name')
        storagedomain     = request.POST.get('storagedomain')
        physical          = request.POST.get('physical')
        profile           = request.POST.get('profile')
        ip1               = request.POST.get('ip1')
        mac1              = request.POST.get('mac1')
        ip2               = request.POST.get('ip2')
        mac2              = request.POST.get('mac2')
        ip3               = request.POST.get('ip3')
        mac3              = request.POST.get('mac3')
        ip4               = request.POST.get('ip4')
        mac4              = request.POST.get('mac4')
        iso               = request.POST.get('iso')
        type              = request.POST.get('type')
        puppetclasses     = request.POST.get('puppetclasses')
        parameters        = request.POST.get('parameters')
        ipilo             = request.POST.get('ipilo')
        ipoa              = request.POST.get('ipoa')
        numvms            = int(request.POST.get('numvms'))
        hostgroup         = request.POST.get('hostgroup')
        create            = request.POST.get('create')
        if create == '0':
            create = False
        else:
            create = True
        if physical == 'false':
            physical = False
        else:
            physical = True
        profile = Profile.objects.get(id=profile)
        if profile.maxvms:
            currentvms = len(VM.objects.filter(profile=profile))
            if currentvms + numvms > profile.maxvms:
                return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>Exceeded maximum vms for this profile<p</div>")
        if storagedomain == '' and not physical:
            return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>Storage Domain is needed<p</div>")
        disksize1, disksize2, numinterfaces, requireip, cobbler, foreman = profile.disksize1, profile.disksize2, profile.numinterfaces, profile.requireip, profile.cobbler, profile.foreman
        if type:
            parameters = "type=%s %s" % (type, parameters)
        #MAKE SURE VM DOESNT ALLREADY EXISTS IN DB WITH THIS SAME PROFILE
        vms = VM.objects.filter(name=name).filter(profile=profile)
        if len(vms) > 0:
            return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>VM %s allready exists</div>" % name)
        if not physical and not profile.virtualprovider.type == 'fake' and not profile.autostorage:
            storageresult=checkstorage(numvms,profile.virtualprovider,disksize1,disksize2,storagedomain)
            if storageresult != 'OK':
                return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>%s</div>" % storageresult )
        #VM CREATION IN DB
        newvm = VM(name=name, storagedomain=storagedomain, physical=physical, profile=profile, ip1=ip1, mac1=mac1, ip2=ip2, mac2=mac2, ip3=ip3, mac3=mac3, ip4=ip4, mac4=mac4, puppetclasses=puppetclasses, parameters=parameters, createdby=username, iso=iso, ipilo=ipilo, ipoa=ipoa, hostgroup=hostgroup, create=create)
        success = newvm.save()
        name  = newvm.name
        if success != 'OK':
            return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>%s</div>" % success )
        if numvms > 1:
            successes={ name : "Machine %s successfully created!!!" % name }
            for num in range(2,numvms+1):
                newname = request.POST.get("name_%s" % num)
                newip1  = request.POST.get("ip1_%s" % num)
                newmac1 = request.POST.get("mac1_%s" % num)
                newip2  = request.POST.get("ip2_%s" % num)
                newip3  = request.POST.get("ip3_%s" % num)
                newip4  = request.POST.get("ip4_%s" % num)
                newvm = VM(name=newname, storagedomain=storagedomain, physical=physical, profile=profile, ip1=newip1, mac1=newmac1, ip2=newip2, mac2=mac2, ip3=newip3, mac3=mac3, ip4=newip4, mac4=mac4, puppetclasses=puppetclasses, parameters=parameters, createdby=username, iso=iso, ipilo=ipilo, ipoa=ipoa, hostgroup=hostgroup)
                success = newvm.save()
                newname = newvm.name
                if success == 'OK':
                    successes[newname]="Machine %s successfully created!!!" % newname
                else:
                    successes[newname]=success
        if request.is_ajax():
            if numvms ==1:
                vmid = newvm.id
                if newvm.physical and newvm.ipilo:
                    default = getdefault()
                    consoleurl = "<a href='https://%s:%s/?ssh=ssh://root@%s:22/'>" % (default.consoleip , default.consoleport, newvm.ipilo )
                else:
                    consoleurl = "<a href='%s/vms/console/?id=%s'>" % ( baseurl, vmid )
                return HttpResponse("<div class='alert alert-success' ><button type='button' class='close' data-dismiss='alert'>&times;</button>Machine %s successfully created!!!access its console %shere</a></div>" % (name, consoleurl) )
            else:
                return HttpResponse("<div class='alert alert-info' ><button type='button' class='close' data-dismiss='alert'>&times;</button>%s</div>" % " ".join(successes.values()) )

        else:
            return render(request, 'create.html', { 'created': True,'name': name, 'username': username  } )
    else:
        vmform =  VMForm(request.user)
        customforms=[]
        if os.path.exists("%s/portal/customtypes.py" % settings.PWD):
            import customtypes
            reload(customtypes)
            for element in dir(customtypes):
                if not element.startswith("__") and element != "forms":
                    exec("customform=customtypes.%s()" % element)
                    customforms.append({'name':element,'form':customform})
            return render(request, 'create.html', { 'vmform': vmform, 'username': username , 'customforms' : customforms  } )
        else:
            return render(request, 'create.html', { 'vmform': vmform, 'username': username } )

@login_required
def profiles(request):
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    groups            = username.groups
    profiles=Profile.objects.all()
    if request.method == 'POST' and request.is_ajax():
        profile = request.POST['profile']
        profile=Profile.objects.get(name=profile)
        cobblerprofile=profile.name
        if profile.cobblerprofile:
            cobblerprofile=profile.cobblerprofile
        return HttpResponse("<div class='alert alert-success' ><button type='button' class='close' data-dismiss='alert'>&times;</button>Cobbler Profile: %s<p><p>Datacenter: %s<p>Cluster: %s<p>Number of cpus: %s<p>Memory: %sMo<p>Guestid: %s<p>Disksize first disk : %sGb<p>Number of network interfaces: %s<p>Foreman Enabled: %s<p>Cobbler Enabled:%s<p>Isos List Enabled: %s<p>Virtual Provider: %s<p>Physical Provider: %s<p>VNC: %s<p></div>" % (cobblerprofile, profile.datacenter, profile.clu, profile.numcpu, profile.memory, profile.guestid, profile.disksize1, profile.numinterfaces, profile.foreman, profile.cobbler, profile.iso, profile.virtualprovider, profile.physicalprovider, profile.vnc ))
    elif username.is_staff:
        profiles = Profile.objects.all()
        if not profiles:
            information = { 'title':'Missing elements' , 'details':'Create profiles first...' }
            return render(request, 'information.html', { 'information' : information , 'username': username } )
        else:
            return render(request, 'profiles.html', { 'profiles': profiles , 'username': username } )
    else:
        usergroups=[]
        for g in groups.values():
            usergroups.append(g['id'])
        if len(usergroups) == 0:
            query = Q(groups=None)
        else:
            query = Q(groups=None)|Q(groups=usergroups[0])
            for group in usergroups[1:]:
                query=query|Q(groups=group)
        query=Profile.objects.filter(query)
        if not query:
            information = { 'title':'Missing elements' , 'details':'Create profiles first...' }
            return render(request, 'information.html', { 'information' : information } )
        else:
            return render(request, 'profiles.html', { 'profiles': query , 'username': username } )

#@login_required
def storage(request):
    logging.debug('prout')
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    if request.is_ajax() and request.method == 'POST':
        virtualprovider = request.POST.get('virtualprovider')
        virtualprovider = VirtualProvider.objects.filter(name=virtualprovider)[0]
        connection = checkconn(virtualprovider.host,virtualprovider.port)
        if not connection:
            errorinfo=[ { 'failure' : "Host %s cant be reached" % virtualprovider.host } ]
            errorinfo = json.dumps(errorinfo)
            return HttpResponse(errorinfo,mimetype='application/json')
        if virtualprovider.type == 'ovirt':
            ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
            storageinfo = ovirt.getstorage()
            ovirt.close()
            #add storage domains to DB if they dont exist
            for stor in storageinfo.keys():
                if not Storage.objects.filter(name=stor).exists():
                    datacenter = storageinfo[stor][2]
                    storage=Storage(name=stor,type=virtualprovider.type,provider=virtualprovider,datacenter=datacenter)
                    storage.save()
            storageinfo = json.dumps(storageinfo)
            return HttpResponse(storageinfo,mimetype='application/json')
        elif virtualprovider.type == 'kvirt':
            kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
            storageinfo = kvirt.getstorage()
            kvirt.close()
            #add storage domains to DB if they dont exist
            for stor in storageinfo.keys():
                if not Storage.objects.filter(name=stor).exists():
                    datacenter = storageinfo[stor][2]
                    storage=Storage(name=stor,type=virtualprovider.type,provider=virtualprovider,datacenter=datacenter)
                    storage.save()
            storageinfo = json.dumps(storageinfo)
            return HttpResponse(storageinfo,mimetype='application/json')
        elif virtualprovider.type == 'vsphere':
            jythoncommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s" % (settings.PWD, 'getstorage', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu )
            storageinfo = os.popen(jythoncommand).read()
            storageinfo= ast.literal_eval(storageinfo)
            #add storage domains to DB if they dont exist
            for stor in storageinfo.keys():
                if not Storage.objects.filter(name=stor).exists():
                    datacenter = storageinfo[stor][2]
                    storage=Storage(name=stor,type=virtualprovider.type,provider=virtualprovider,datacenter=datacenter)
                    storage.save()
            storageinfo = json.dumps(storageinfo)
            return HttpResponse(storageinfo,mimetype='application/json')
        elif virtualprovider.type == 'vsphere2':
	    vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
            storageinfo = vsphere.getstorage()
            vsphere.close()
            #add storage domains to DB if they dont exist
            for stor in storageinfo.keys():
                if not Storage.objects.filter(name=stor).exists():
                    datacenter = storageinfo[stor][2]
                    storage=Storage(name=stor,type=virtualprovider.type,provider=virtualprovider,datacenter=datacenter)
                    storage.save()
            storageinfo = json.dumps(storageinfo)
            return HttpResponse(storageinfo,mimetype='application/json')
    else:
        if username.is_staff:
            vproviders=VirtualProvider.objects.filter(Q(type='ovirt')|Q(type='vsphere')|Q(type='kvirt')|Q(type='vsphere2'))
        else:
            usergroups = []
            groups            = username.groups
            for g in groups.values():
                usergroups.append(g['id'])
            if len(usergroups) == 0:
                query = Q(groups=None)
            else:
                query = Q(groups=None)|Q(groups=usergroups[0])
                for group in usergroups[1:]:
                    query = query|Q(groups=group)
            query = Profile.objects.filter(query)
            if not query:
                information = { 'title':'Missing elements' , 'details':'Create Profiles first...' }
                return render(request, 'information.html', { 'information' : information ,  'username': username } )
            vproviderslist = []
            for profile in query:
                if profile.virtualprovider and profile.virtualprovider.name not in vproviderslist:
                    vproviderslist.append(profile.virtualprovider.name)
            vquery = Q(name=vproviderslist[0])
            for provider in vproviderslist:
                vquery = vquery|Q(name=provider)
            vproviders=VirtualProvider.objects.filter(Q(type='ovirt')|Q(type='vsphere')|Q(type='kvirt')|Q(type='vsphere2'))
            vproviders=vproviders.filter(vquery)
        if not vproviders:
            information = { 'title':'Missing elements' , 'details':'Create Virtual providers first...' }
            return render(request, 'information.html', { 'information' : information ,  'username': username } )
        else:
            form = StorageForm()
            return render(request, 'storage.html', { 'vproviders' : vproviders ,'username': username } )


@login_required
def types(request):
    if request.method == 'POST' or request.is_ajax():
        results=[[]]
        types= request.POST.get('types').split(',')
        otherclasses=[]
        import customtypes
        reload(customtypes)
        for element in dir(customtypes):
            if element in types:
                exec("type=customtypes.%s()" % element)
                for attr in type.fields.keys():
                    results.append(attr)
            elif not element.startswith('__') and element != "forms":
                otherclasses.append(element)
        results[0] = otherclasses
        results = json.dumps(results)
        return HttpResponse(results,mimetype='application/json')

@login_required
def profileinfo(request):
    if request.method == 'POST' or request.is_ajax():
        profile = request.POST.get('profile')
        profile = Profile.objects.filter(id=profile)[0]
        datacenter = profile.datacenter
        specific=[]
        storages=[]
        virtualprovider=profile.virtualprovider
        type=virtualprovider.type
        if type != "fake":
            provider = "%s,%s" % (virtualprovider.id, virtualprovider.name)
            if profile.autostorage:
                #RETRIEVE BEST STORAGE DOMAIN
                if type == 'ovirt':
                    ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
                    storages = [ovirt.beststorage(datacenter)]
                    ovirt.close()
                elif type == 'kvirt':
                    kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
                    storages = [kvirt.beststorage()]
                    kvirt.close()
                elif type == 'vsphere':
                    beststoragecommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s" % (settings.PWD,'beststorage', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu)
                    bestds = os.popen(beststoragecommand).read()
                    storages=[bestds.strip()]
                elif type == 'vsphere2':
 		    vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
                    storages = [vsphere.beststorage()]
                    vsphere.close()
                else:
                    storages=["N/A"]
            else:
                storagelist=Storage.objects.filter(provider=virtualprovider,datacenter=datacenter)
                for stor in storagelist:
                    storages.append(stor.name)
        else:
            provider = "%s,%s" % (virtualprovider.id, virtualprovider.name)
            storages=['N/A']
        if type =='ovirt' and profile.iso:
            type = 'iso'
            specific=[]
            ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
            isos  = ovirt.getisos()
            ovirt.close()
            for iso in isos:
                specific.append(iso)
        if type =='kvirt' and profile.iso:
            type = 'iso'
            specific=[]
            kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
            isos  = kvirt.getisos()
            kvirt.close()
            for iso in isos:
                specific.append(iso)
        if type =='vsphere' and profile.iso:
            type = 'iso'
            isocommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s" % (settings.PWD,'getisos', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu)
            isocommand = os.popen(isocommand).read()
            isos       = ast.literal_eval(isocommand)
            for iso in isos:
                specific.append(iso)
        if type =='vsphere2' and profile.iso:
            type      = 'iso'
            specific  = []
	    vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
            isos      = vsphere.getisos()
            vsphere.close()
            for iso in isos:
                specific.append(iso)
        results = [type,profile.hide ,provider,specific,profile.foreman, profile.cobbler,profile.numinterfaces,storages]
        if profile.cobbler:
            cobblerprovider=profile.cobblerprovider
            cobblerprovider = "%s,%s" % (cobblerprovider.id, cobblerprovider.name)
            results.append(cobblerprovider)
        else:
            results.append('')
        if profile.foreman:
            foremanprovider=profile.foremanprovider
            foremaninfo = "%s,%s" % (foremanprovider.id, foremanprovider.name)
            results.append(foremaninfo)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((foremanprovider.host, foremanprovider.port))
                available = True
            except socket.error:
                available=False
            if available:
                foremanhost, foremanport, foremansecure, foremanuser, foremanpassword, foremanenv = foremanprovider.host, foremanprovider.port, foremanprovider.secure, foremanprovider.user, foremanprovider.password , foremanprovider.envid
                foreman= Foreman(host=foremanhost, port=foremanport,user=foremanuser, password=foremanpassword, secure=foremansecure)
                if profile.foremanenv:
                    foremanenv = profile.foremanenv
                hostgroups = ['']
                hostgroups.extend(foreman.hostgroups(foremanenv))
                results.append(hostgroups)
                classes = foreman.classes(foremanenv)
                results.append(classes)
            else:
                results.append([''])
        else:
            results.append('')

        results = json.dumps(results)
        return HttpResponse(results,mimetype='application/json')

@login_required
def virtualprovidertype(request):
    if request.method == 'POST' or request.is_ajax():
        virtualprovider = request.POST.get('virtualprovider')
        virtualprovider = VirtualProvider.objects.filter(id=virtualprovider)[0]
        results = [virtualprovider.type]
        if virtualprovider.type == 'ilo' and request.POST.has_key('ipilo'):
            ipilo = request.POST.get('ipilo')
            ilo=Ilo(ipilo,virtualprovider.user,virtualprovider.password)
            macs = ilo.getmacs()
            for mac in macs:
                results.append(mac)
        if virtualprovider.type == 'oa' and request.POST.has_key('ipilo') and request.POST.has_key('name'):
            name = request.POST.get('name')
            ipilo = request.POST.get('ipilo')
            oa=Oa(ipilo,virtualprovider.user,virtualprovider.password)
            bladeid = oa.getid(name)
            macs = oa.getmacs(bladeid)
            for mac in macs:
                results.append(mac)
        if virtualprovider.type == 'ovirt' and request.POST.has_key('profile'):
            profile = request.POST.get('profile')
            profile = Profile.objects.filter(id=profile)[0]
            if profile.iso:
                ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
                isos = ovirt.getisos()
                ovirt.close()
                results=['iso']
                for iso in isos:
                    results.append(iso)
        if virtualprovider.type == 'kvirt' and request.POST.has_key('profile'):
            profile = request.POST.get('profile')
            profile = Profile.objects.filter(id=profile)[0]
            if profile.iso:
                kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
                isos = kvirt.getisos()
                kvirt.close()
                results=['iso']
                for iso in isos:
                    results.append(iso)
        results = json.dumps(results)
        return HttpResponse(results,mimetype='application/json')

@login_required
def yourvms(request):
    ajax = False
    if request.is_ajax():
        ajax = True
    allvms = {}
    username          = request.user.username
    username          = User.objects.get(username=username)
    usergroups        = username.groups
    query             = Q(createdby=username)
    allusers          = User.objects.all()
    for g in usergroups.all():
        for u in allusers:
            if u.username == username.username:
                continue
            if g in u.groups.all():
                query=query|Q(createdby=u)
    vms = VM.objects.filter(query)
    resultvms=[]
    actives=[]
    inactives=[]
    for vm in vms:
        name = vm.name
        if not ajax:
            vm.status = "Please wait"
            resultvms.append(vm)
            continue
        if vm.unmanaged:
            vm.status = "unmanaged"
            resultvms.append(vm)
            continue
        #handle physical machines
        if vm.physical:
            physicalprovider=vm.profile.physicalprovider
            if physicalprovider in inactives:
                vm.status = 'N/A'
                resultvms.append(vm)
                continue
            try:
                if physicalprovider.type =='ilo':
                    iptocheck=vm.ipilo
                if physicalprovider.type =='oa':
                    iptocheck=vm.ipoa
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect((iptocheck, 22))
                if physicalprovider.type =='ilo':
                    ilo=Ilo(vm.ipilo,physicalprovider.user,physicalprovider.password)
                    status = ilo.status()
                elif physicalprovider.type =='oa':
                    oa=Oa(vm.ipoa,physicalprovider.user,physicalprovider.password)
                    bladeid =oa.getid(name)
                    status = oa.status(bladeid)
                vm.status = status
                resultvms.append(vm)
                continue
            except:
                inactives.append(physicalprovider)
                vm.status = 'N/A'
                resultvms.append(vm)
                continue
        virtualprovider = vm.profile.virtualprovider
        if virtualprovider in inactives:
            vm.status = 'N/A'
            resultvms.append(vm)
            continue
        elif not virtualprovider in actives:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect((virtualprovider.host, virtualprovider.port))
                actives.append(virtualprovider)
            except socket.error:
                inactives.append(virtualprovider)
                vm.status = 'N/A'
                resultvms.append(vm)
                continue
        if not vm.physical and virtualprovider.type == 'ovirt':
            if not allvms.has_key(virtualprovider.name):
                ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
                allvms[virtualprovider.name] = ovirt.allvms()
            if allvms[virtualprovider.name].has_key(name):
                status = allvms[virtualprovider.name][name]
            else:
                status = 'NotFound'
        if not vm.physical and virtualprovider.type == 'kvirt':
            if not allvms.has_key(virtualprovider.name):
                kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
                allvms[virtualprovider.name] = kvirt.allvms()
                kvirt.close()
            if allvms[virtualprovider.name].has_key(name):
                status = allvms[virtualprovider.name][name]
            else:
                status = 'NotFound'
        if not vm.physical and virtualprovider.type == 'vsphere':
            if not allvms.has_key(virtualprovider.name):
                allvmscommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s" % (settings.PWD,'allvms', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu)
                allvmscommand = os.popen(allvmscommand).read()
                allvms[virtualprovider.name] = ast.literal_eval(allvmscommand)
            if allvms[virtualprovider.name].has_key(name):
                status = allvms[virtualprovider.name][name]
            else:
                status = 'NotFound'
        if not vm.physical and virtualprovider.type == 'vsphere2':
            if not allvms.has_key(virtualprovider.name):
                vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
                allvms[virtualprovider.name] = vsphere.allvms()
                vsphere.close()
            if allvms[virtualprovider.name].has_key(name):
                status = allvms[virtualprovider.name][name]
            else:
                status = 'NotFound'
        if not vm.physical and virtualprovider.type == 'fake':
            status = "N/A"
        vm.status = status
        resultvms.append(vm)
    if ajax:
        return render(request, 'yourvms2.html', { 'vms': resultvms, 'username': username , 'ajax' : ajax } )
    else:
        return render(request, 'yourvms.html', { 'vms': resultvms, 'username': username  } )

@login_required
def allvms(request):
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    if not username.is_staff:
        information = { 'title':'Nuages Restricted Information' , 'details':'Restricted access,sorry....' }
        return render(request, 'information.html', { 'information' : information } )
    if request.method == 'POST' or request.is_ajax():
        resultvms=[]
        virtualprovidername = request.POST.get('virtualprovider')
        virtualprovider = VirtualProvider.objects.filter(name=virtualprovidername)[0]
        if virtualprovider.type == 'ovirt':
            ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
            vms = ovirt.allvms()
            ovirt.close()
            for vm in vms:
                resultvms.append( {'name':vm, 'status':vms[vm],'virtualprovider':virtualprovidername } )
        if virtualprovider.type == 'kvirt':
            kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
            vms = kvirt.allvms()
            kvirt.close()
            for vm in vms:
                resultvms.append( {'name':vm, 'status':vms[vm],'virtualprovider':virtualprovidername } )
        if virtualprovider.type == 'vsphere':
            allvmscommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s" % (settings.PWD,'allvms', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu)
            results = os.popen(allvmscommand).read()
            vms= ast.literal_eval(results)
            for vm in vms:
                resultvms.append( {'name':vm, 'status':vms[vm],'virtualprovider':virtualprovidername } )
        if virtualprovider.type == 'vsphere2':
	    vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
            vms       = vsphere.allvms()
            vsphere.close()
            for vm in vms:
                resultvms.append( {'name':vm, 'status':vms[vm],'virtualprovider':virtualprovidername } )
        return render(request, 'allvms2.html', { 'vms': resultvms, 'console' : True , 'username': username } )
    else:
        vproviders=VirtualProvider.objects.filter(Q(type='ovirt')|Q(type='vsphere')|Q(type='kvirt')|Q(type='vsphere2'))
        return render(request, 'allvms.html', { 'vproviders' : vproviders , 'username': username } )


@login_required
def console(request):
    username          = request.user.username
    username          = User.objects.get(username=username)
    usergroups        = username.groups
    keyboard          = request.session.get('keyboard')
    if request.method == 'GET':
        if request.GET.has_key('id'):
            vmid = request.GET.get('id')
            vm = VM.objects.get(id=vmid)
            vmname = vm.name
            virtualprovidername = vm.profile.virtualprovider
            vmcreatedby = vm.createdby.username
            if vmcreatedby !=username.username:
                vmgroups = vm.createdby.groups
                commongroup = False
                for group in vmgroups.all():
                    if group in usergroups.all():
                        commongroup = True
                        break
                if not commongroup:
                    information = { 'title':'Console not authorized' , 'details':'Your user is not authorized to access this VM' }
                    return render(request, 'information.html', { 'information' : information } )
        if request.GET.has_key('name') and request.GET.has_key('virtualprovider') and username.is_staff:
            vmname = request.GET.get('name')
            virtualprovidername = request.GET.get('virtualprovider')
        virtualprovider = VirtualProvider.objects.get(name=virtualprovidername)
        default = getdefault()
        sockhost=default.consoleip
        sockport = random.randint(default.consoleminport,default.consolemaxport)
        if default.consolesecure:
            sockprotocol = 'wss'
        else:
            sockprotocol = 'ws'
        pwd = settings.PWD
        if virtualprovider.type == 'ovirt' or virtualprovider.type == 'kvirt':
            if virtualprovider.type == 'ovirt':
                ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
                host, port, ticket, protocol = ovirt.console(vmname)
                ovirt.close()
                if not host:
                    information = { 'title' : 'Console not accessible' , 'details' : 'Machine %s doesnt seem to be up.Refresh page...' % vmname }
                    return render(request, 'information.html', { 'information' : information } )
            if virtualprovider.type == 'kvirt':
                kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
                host, port, ticket, protocol = kvirt.console(vmname)
                kvirt.close()
                if not host:
                    information = { 'title':'Console not configured' , 'details':'No display found' }
                    return render(request, 'information.html', { 'information' : information , 'default' : default } )
            if virtualprovider.type == 'vsphere2':
		vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
                host, port = vsphere.console(vmname)
                #vsphere.close()
            	if host != None and  checkconn(host,int(port)):
                	pwd = settings.PWD
                	websockifycommand = "websockify %s -D --timeout=30 %s:%s" % (sockport,host,port)
                	os.popen(websockifycommand)
                	information = { 'host' : sockhost , 'port' : sockport  }
                	vm = {'name': vmname , 'virtualprovider' : virtualprovider , 'status' : 'up' }
                	return render(request, 'vnc.html', { 'information' : information ,  'vm' : vm , 'username': username , 'default' : default  } )
		else:
			if not virtualprovider.sha1 or not virtualprovider.fqdn:
				virtualprovider.fqdn, virtualprovider.sha1 = getvspherecert(virtualprovider.host)
				if fqdn == None or sha1 == None:
					information = { 'title':'Wrong Console' , 'details':"Missing python-ssl and python-crypto modules. Report to admin" }
					return render(request, 'information.html', { 'information' : information , 'default' : default } )
				virtualprovider.save()
			fqdn, sha1 = virtualprovider.fqdn, virtualprovider.sha1
			consoleurl = vsphere.html5console(vmname,fqdn,sha1)
			return redirect(consoleurl)

            information = { 'host' : sockhost , 'port' : sockport , 'protocol': sockprotocol, 'ticket' : ticket , 'keyboard' : keyboard }
            vm = {'name': vmname , 'virtualprovider' : virtualprovider , 'status' : 'up' }
            if protocol =="spice" and virtualprovider.type == 'ovirt':
                pwd = settings.PWD
                cert="%s/%s.pem" % (pwd,virtualprovider.name)
                websockifycommand = "websockify %s -D --timeout=30 --cert %s --ssl-target %s:%s" % (sockport,cert,host,port)
                os.popen(websockifycommand)
                return render(request, 'spice.html', { 'information' : information ,  'vm' : vm , 'username': username } )
            if protocol =="spice" and virtualprovider.type == 'kvirt':
                pwd = settings.PWD
                #cert="%s/%s.pem" % (settings.PWD,virtualprovider.name)
                #websockifycommand = "websockify %s -D --timeout=30 --cert %s --ssl-target %s:%s" % (sockport,cert,host,port)
                websockifycommand = "websockify %s -D --timeout=30 %s:%s" % (sockport,host,port)
                os.popen(websockifycommand)
                return render(request, 'spice.html', { 'information' : information ,  'vm' : vm , 'username': username , 'default' : default } )
            elif protocol =="vnc":
                websockifycommand = "websockify %s -D --timeout=30 %s:%s" % (sockport,host,port)
                os.popen(websockifycommand)
                return render(request, 'vnc.html', { 'information' : information ,  'vm' : vm , 'username': username , 'default' : default } )
        elif virtualprovider.type == 'vsphere':
		consolecommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s %s" % (settings.PWD,'console', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu , vmname )
		consoledetails = os.popen(consolecommand).read()
		host,port = ast.literal_eval(consoledetails)
		if host != None and  checkconn(host,int(port)):
                	pwd = settings.PWD
                	websockifycommand = "websockify %s -D --timeout=30 %s:%s" % (sockport,host,port)
                	os.popen(websockifycommand)
                	information = { 'host' : sockhost , 'port' : sockport  }
                	vm = {'name': vmname , 'virtualprovider' : virtualprovider , 'status' : 'up' }
                	return render(request, 'vnc.html', { 'information' : information ,  'vm' : vm , 'username': username , 'default' : default  } )
            	else:
			if not virtualprovider.sha1 or not virtualprovider.fqdn:
                    		virtualprovider.fqdn, virtualprovider.sha1 = getvspherecert(virtualprovider.host)
                    		if fqdn == None or sha1 == None:
                        		information = { 'title':'Wrong Console' , 'details':"Missing python-ssl and python-crypto modules. Report to admin" }
                        		return render(request, 'information.html', { 'information' : information , 'default' : default } )
                    		virtualprovider.save()
                		fqdn, sha1 = virtualprovider.fqdn, virtualprovider.sha1
                		pwd = settings.PWD
                		consolecommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s %s %s %s" % (settings.PWD,'html5console', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu , vmname, fqdn, sha1 )
                		consoleurl = os.popen(consolecommand).read().strip()
                		print consoleurl
                		return redirect(consoleurl)
	elif virtualprovider.type == 'vsphere2':
		vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
                host, port = vsphere.console(vmname)
                vsphere.close()
            	if host != None and  checkconn(host,int(port)):
                	pwd = settings.PWD
                	websockifycommand = "websockify %s -D --timeout=30 %s:%s" % (sockport,host,port)
                	os.popen(websockifycommand)
                	information = { 'host' : sockhost , 'port' : sockport  }
                	vm = {'name': vmname , 'virtualprovider' : virtualprovider , 'status' : 'up' }
                	return render(request, 'vnc.html', { 'information' : information ,  'vm' : vm , 'username': username , 'default' : default  } )
		else:
			if not virtualprovider.sha1 or not virtualprovider.fqdn:
				virtualprovider.fqdn, virtualprovider.sha1 = getvspherecert(virtualprovider.host)
				if fqdn == None or sha1 == None:
					information = { 'title':'Wrong Console' , 'details':"Missing python-ssl and python-crypto modules. Report to admin" }
					return render(request, 'information.html', { 'information' : information , 'default' : default } )
				virtualprovider.save()
			fqdn, sha1 = virtualprovider.fqdn, virtualprovider.sha1
			consoleurl = vsphere.html5console(vmname,fqdn,sha1)
			print consoleurl
			return redirect(consoleurl)
    else:
        information = { 'title':'Wrong Console' , 'details':"something went wrong. Report to sysadmin" }
        return render(request, 'information.html', { 'information' : information  } )


@login_required
def start(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        virtualprovider=request.POST.get('virtualprovider')
        virtualprovider = VirtualProvider.objects.get(name=virtualprovider)
        results = vmstart(name, virtualprovider)
        if virtualprovider.type == 'vsphere':
            return HttpResponse(results, mimetype='application/json')
        else:
            return HttpResponse(results)

@login_required
def stop(request):
    if request.method == 'POST':
        name            = request.POST.get('name')
        virtualprovider = request.POST.get('virtualprovider')
        virtualprovider = VirtualProvider.objects.get(name=virtualprovider)
        results = vmstop(name, virtualprovider)
        if virtualprovider.type == 'vsphere':
            return HttpResponse(results,mimetype='application/json')
        else:
            return HttpResponse(results)

@login_required
def kill(request):
    logging.debug('prout')
    if request.method == 'POST':
        name     = request.POST.get('name')
        profile  = request.POST.get('profile')
        profile  = Profile.objects.get(name=profile)
        vm       = VM.objects.filter(name=name).filter(profile=profile)[0]
        vm.kill()
        vm.unmanaged = True
        vm.save()
        if profile.fulldelete:
            vm.delete()
        return HttpResponse("VM %s killed" % name)

def dbremove(request):
    if request.method == 'POST':
        vmid     = request.POST.get('id')
        vmname   = request.POST.get('name')
        vm       = VM.objects.get(id=vmid)
        if vm.unmanaged:
            vm.delete()
            return HttpResponse("VM %s removed from DB" % vmname)
        else:
            return HttpResponse("VM %s not removed from DB as still managed" % vmname)

@login_required
def hostgroups(request):
    if request.method == 'POST':
        profile=request.POST.get('profile')
        profile = Profile.objects.get(name=profile)
        foreman = profile.foreman
        if not foreman:
            return HttpResponse(json.dumps([]), mimetype='application/json')
        foremanprovider = profile.foremanprovider
        foremanhost, foremanport, foremansecure, foremanuser, foremanpassword, foremanenv = foremanprovider.host, foremanprovider.port,foremanprovider.secure, foremanprovider.user, foremanprovider.password, foremanprovider.envid
        foreman=Foreman(host=foremanhost,port=foremanport,user=foremanuser, password=foremanpassword, secure=foremansecure)
        if profile.foremanenv:
            foremanenv = profile.foremanenv
        hostgroups = ['']
        hostgroups.extend(foreman.hostgroups(foremanenv))
        hostgroups = json.dumps(hostgroups)
        return HttpResponse(hostgroups, mimetype='application/json')

@login_required
def customforms(request):
    logging.debug('prout')
    if not os.path.exists("%s/portal/customtypes.py" % settings.PWD ):
        information = { 'title':'No customforms' , 'details':'No customforms found.' }
        return render(request, 'information.html', { 'information' : information ,  'username': username } )
    import customtypes
    reload(customtypes)
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    if request.method == 'POST' and request.POST.has_key('type'):
        type= request.POST.get('type')
        attributes=[]
        exec("type=customtypes.%s()" % type)
        for attr in type.fields:
            if 'max_length' in type.fields[attr].__dict__:
                fieldname='CharField'
                specific=type.fields[attr].initial
            elif '_choices' in type.fields[attr].__dict__:
                fieldname='ChoiceField'
                #specific=type.fields[attr].choices
                specific=[]
                for element in type.fields[attr].choices:
                    specific.append(element[0])
            elif 'max_value' in type.fields[attr].__dict__:
                fieldname='IntegerField'
                specific=type.fields[attr].initial
            attributes.append([attr,fieldname,specific,type.fields[attr].required])
        attributes = json.dumps(attributes)
        return HttpResponse(attributes,mimetype='application/json')
    else:
        types=[]
        for element in dir(customtypes):
            if not element.startswith('__') and element != "forms":
                types.append(element)
        return render(request, 'customforms.html', { 'username': username , 'types': types } )


@login_required
def customforminfo(request):
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    if request.method == 'POST':
        type= request.POST.get('type')
        exec("type=%s()" % type)
        return HttpResponse(type.as_table())
    else:
        types=[]
        import customtypes
        reload(customtypes)
        for element in dir(customtypes):
            if not element.startswith('__') and element != "forms":
                types.append(element)
        return render(request, 'customforms.html', { 'username': username , 'types': types } )

@login_required
def customformedit(request):
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    if not os.path.exists("%s/portal/customtypes.py" % settings.PWD ):
        return render(request, 'customformedit.html', { 'username': username  } )
    import customtypes
    reload(customtypes)
    if request.method == 'POST' and request.POST.has_key('type'):
        type= request.POST.get('type')
        attributes=[]
        #exec("type=%s()" % type)
        exec("type=customtypes.%s()" % type)
        for attr in type.fields:
            #required = type.fields[attr].required
            required = False
            if 'max_length' in type.fields[attr].__dict__:
                fieldname='CharField'
                specific=type.fields[attr].initial
            elif '_choices' in type.fields[attr].__dict__:
                fieldname='ChoiceField'
                #specific=type.fields[attr].choices
                specific=[]
                for element in type.fields[attr].choices:
                    specific.append(element[0])
            elif 'max_value' in type.fields[attr].__dict__:
                fieldname='IntegerField'
                specific=type.fields[attr].initial
            attributes.append([attr,fieldname,specific,required])
        attributes = json.dumps(attributes)
        return HttpResponse(attributes,mimetype='application/json')
    else:
        types=[]
        for element in dir(customtypes):
            if not element.startswith('__') and element != "forms":
                types.append(element)
        if request.is_ajax():
            types = json.dumps(types)
            return HttpResponse(types,mimetype='application/json')
        else:
            return render(request, 'customformedit.html', { 'username': username , 'types': types } )

@login_required
def customformcreate(request):
    if request.method == 'POST' and request.POST.has_key('type'):
        type = request.POST['type'].capitalize()
        if not os.path.exists("%s/portal/customtypes.py" % settings.PWD ) or not  open("%s/portal/customtypes.py" % settings.PWD ).readlines():
            f=open("%s/portal/customtypes.py" % settings.PWD ,"a")
            f.write("from django import forms\n")
            f.close()
        if os.path.exists('/tmp/customtypes.py.lock' ):
            response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>customtypes  currently edited by another user</div>"
            return HttpResponse(response)
        else:
            #open lock file
            open('/tmp/customtypes.py.lock' , 'a').close()
            types=[]
            import customtypes
            reload(customtypes)
            for element in dir(customtypes):
                if not element.startswith('__') and element != "forms":
                    types.append(element)
            if type in types:
                os.remove('/tmp/customtypes.py.lock' )
                response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>customform allready existing</div>"
                return HttpResponse(response)
            else:
                f = open("%s/portal/customtypes.py" % settings.PWD , 'a')
                f.write("\nclass %s(forms.Form):\n" % type)
                f.write("\tpass\n")
                f.close()
                #remove lock file
                os.remove('/tmp/customtypes.py.lock' )
                response = "<div class='alert alert-success'><button type='button' class='close' data-dismiss='alert'>&times;</button>Custom form %s created</div>" % type
                return HttpResponse(response)

@login_required
def customformupdate(request):
    if request.method == 'POST' and request.POST.has_key('parameters') and request.POST.has_key('type'):
        type = request.POST['type'].capitalize()
        parameters = request.POST['parameters']
        if not os.path.exists("%s/portal/customtypes.py" % settings.PWD ) or not  open("%s/portal/customtypes.py" % settings.PWD ).readlines():
            f=open("%s/portal/customtypes.py" % settings.PWD ,"a")
            f.write("from django import forms\n")
            f.close()
        if os.path.exists('/tmp/customtypes.py.lock' ):
            response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>customtypes  currently edited by another user</div>"
            return HttpResponse(response)
        else:
            #open lock file
            open('/tmp/customtypes.py.lock' , 'a').close()
            types=[]
            import customtypes
            reload(customtypes)
            for element in dir(customtypes):
                if not element.startswith('__') and element != "forms":
                    types.append(element)
            #it s an existing type, we must first remove  along with all of its attribute
            if type in types:
                attributes=["pass"]
                exec("form=%s()" % type)
                for attr in form.fields:
                    attributes.append(attr)
                attributes.insert(0,type)
                #NOW WE NEED TO PARSE THE FILE AND REMOVE ACCORDINGLY LINES!!!!
                for line in fileinput.input("%s/portal/customtypes.py" % settings.PWD, inplace=True):
                    found = False
                    for attribute in attributes:
                        if attribute in line:
                            found = True
                            break
                    if not found:
                        print line,
            #now add it at the end of  customtypes.py
            #completefile = open("%s/portal/customtypes.py" % settings.PWD).readlines()
            parameters = parameters.split(' ')
            #preliminary check for  uniqueness of parameters
            #for parameter in parameters:
            #       parameter=parameter.split(';')
            #       name=parameter[0]
            #       indices = [i for i, x in enumerate(completefile) if name in x ]
            #       if len(indices) >1:
            #               response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>parameter names need to be unique</div>"
            #               return HttpResponse(response)
            f = open("%s/portal/customtypes.py" % settings.PWD , 'a')
            f.write("\nclass %s(forms.Form):\n" % type)
            for parameter in parameters:
                parameter=parameter.split(';')
                name=parameter[0]
                fieldtype=parameter[1]
                default=parameter[2]
                required=parameter[3]
                if required:
                    required= ',blank=true, null=True'
                else:    
                    required = ''
                if fieldtype == "IntegerField" and default != '':
                    f.write("\t%s\t= forms.%s(initial=%s%s)\n" % (name,fieldtype,int(default), required ) )
                elif fieldtype == "CharField" and default != '':
                    f.write("\t%s\t= forms.%s(initial=\"%s\"%s)\n" % (name,fieldtype,default, required ) )
                elif fieldtype == "ChoiceField" and default != '':
                    choices=''
                    for choice in default.split(','):
                        if choices == '':
                            choices = "('%s', '%s')" % (choice,choice)
                        else:
                            choices = choices+",('%s', '%s')" % (choice,choice)
                    f.write("\t%s\t= forms.%s(choices=(%s)%s)\n" % (name,fieldtype,choices, required ) )
                else:
                    if len(required) >0:
                        required= 'blank=true, null=True'
                    f.write("\t%s\t= forms.%s(%s)\n" % (name,fieldtype) )
            f.close()
            #remove lock file
            os.remove('/tmp/customtypes.py.lock'  )
            response = "<div class='alert alert-success'><button type='button' class='close' data-dismiss='alert'>&times;</button>Custom form %s updated</div>" % type
            return HttpResponse(response)

@login_required
def customformdelete(request):
    if request.method == 'POST' and request.POST.has_key('type'):
        type = request.POST['type'].capitalize()
        if os.path.exists('/tmp/customtypes.py.lock' ):
            response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>customtypes  currently edited by another user</div>"
            return HttpResponse(response)
        else:
            #open lock file
            open('/tmp/customtypes.py.lock' , 'a').close()
            types=[]
            import customtypes
            reload(customtypes)
            attributes=[]
            exec("form=%s()" % type)
            for attr in form.fields:
                attributes.append(attr)
            attributes.insert(0,type)
            #NOW WE NEED TO PARSE THE FILE AND REMOVE ACCORDINGLY LINES!!!!
            for line in fileinput.input("%s/portal/customtypes.py" % settings.PWD , inplace=True):
                found = False
                for attribute in attributes:
                    if attribute in line:
                        found = True
                        break
                if not found:
                    print line,
            #remove lock file
            os.remove('/tmp/customtypes.py.lock' )
            response = "<div class='alert alert-success'><button type='button' class='close' data-dismiss='alert'>&times;</button>Custom form %s deleted</div>" % type
            return HttpResponse(response)

#@login_required
def invoicepdf(request):
    try:
        from reportlab.pdfgen import canvas
    except:
        information = { 'title':'Missing library' , 'details':'python-reportlab missing.Contact administrator...' }
        return render(request, 'information.html', { 'information' : information   } )
    try:
        from dateutil.relativedelta import relativedelta
    except:
        information = { 'title':'Missing library' , 'details':'python-dateutil missing.Contact administrator...' }
        return render(request, 'information.html', { 'information' : information  } )
    if request.method == 'GET' and request.GET.has_key('id'):
        #now      = datetime.now()
        now      = timezone.now()
        nowday   = now.strftime("%d")
        nowmonth = now.strftime("%Y-%m")
        default = getdefault()
        currency = default.currency
        vmid = request.GET.get('id')
        vm = VM.objects.get(id=vmid)
        price = vm.price
        virtualprovider = vm.profile.virtualprovider.name
        name = vm.name
        createdwhen = vm.createdwhen
        month    = createdwhen.strftime("%Y-%m")
        day      = createdwhen.strftime("%d")
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="%s_%s_%s"' % (now.strftime("%Y-%m-%d"),virtualprovider,vm.name)
        p = canvas.Canvas(response)
        p.setLineWidth(.3)
        p.setFont('Helvetica', 12)
        p.drawString(30,750,'Billing information regarding VM %s' % name)
        p.drawString(30,735,"From provider %s" % virtualprovider)
        p.drawString(500,750,"Date: %s" % now().strftime("%Y-%m-%d"))
        p.drawString(275,725,'Price per day:')
        p.drawString(500,725,"%s" % vm.price+currency)
        p.line(378,723,580,723)
        p.drawString(30,703,'Owner:')
        #p.line(120,700,580,700)
        p.drawString(120,703,"%s" % vm.createdby)
        p.drawString(30,680,'Month:')
        #p.line(120,700,580,700)
        p.drawString(120,680,"Total price:")
        y = 660
        #at least this time
        if month != nowmonth:
            firstyear,firstmonth=month.split('-')
            numdays = monthrange(int(firstyear),int(firstmonth))[1]
            totaldays = int(numdays) -int(day) +1
            total = str(totaldays*price)+currency
            p.drawString(30,y,"%s" % month)
            p.drawString(120,y,total)
            y = y -20
            month = createdwhen+ relativedelta(months=1)
            month = month.strftime("%Y-%m")
            while month != nowmonth:
                month    = month.strftime("%Y-%m")
                currentyear,currentmonth=month.split('-')
                numdays = monthrange(int(currentyear),int(currentmonth))[1]
                total = str(int(numdays)*price)+currency
                p.drawString(30,y,"%s" % month)
                p.drawString(120,y,total)
                y = y -20
                month = createdwhen+ relativedelta(months=1)
                month = month.strftime("%Y-%m")
            total = str(int(nowday)*price)+currency
            p.drawString(30,y,"%s" % month)
            p.drawString(120,y,total)

        else:
            #now      = datetime.now()
            now      = timezone.now()
            nowday   = now.strftime("%d")
            nowmonth = now.strftime("%Y-%m")
            total = str((int(nowday)-int(day))*price)+currency
            p.drawString(30,y,"%s" % nowmonth)
            p.drawString(120,y,total)
            y = y -20
        p.showPage()
        p.save()
        return response

@login_required
def invoice(request):
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    try:
        from dateutil.relativedelta import relativedelta
    except:
        information = { 'title':'Missing library' , 'details':'python-dateutil missing.Contact administrator...' }
        return render(request, 'information.html', { 'information' : information } )
    if request.method == 'GET' and request.GET.has_key('id'):
        details = []
        vmid = request.GET.get('id')
        vm = VM.objects.get(id=vmid)
        price = vm.price
        if not price:
            information = { 'title':'Missing information' , 'details':'no invoice available for this VM' }
            return render(request, 'information.html', { 'information' : information } )
        createdwhen = vm.createdwhen
        month    = createdwhen.strftime("%Y-%m")
        day      = createdwhen.strftime("%d")
        #now      = datetime.now()
        now      =timezone.now()
        nowday   = now.strftime("%d")
        nowmonth = now.strftime("%Y-%m")
        #at least this time
        if month != nowmonth:
            firstyear,firstmonth=month.split('-')
            numdays = monthrange(int(firstyear),int(firstmonth))[1]
            totaldays = int(numdays) -int(day) +1
            total = totaldays*price
            details.append({ 'month': month , 'total' : total })
            month = createdwhen+ relativedelta(months=1)
            month = month.strftime("%Y-%m")
            while month != nowmonth:
                month    = month.strftime("%Y-%m")
                currentyear,currentmonth=month.split('-')
                numdays = monthrange(int(currentyear),int(currentmonth))[1]
                total = int(numdays)*price
                details.append({ 'month': month , 'total' : total })
                month = createdwhen+ relativedelta(months=1)
                month = month.strftime("%Y-%m")
            total = int(nowday)*price
            details.append({ 'month': month , 'total' : total  })

        else:
            #now      = datetime.now()
            now      = timezone.now()
            nowday   = now.strftime("%d")
            nowmonth = now.strftime("%Y-%m")
            total = (int(nowday)-int(day))*price
            details.append({ 'month': nowmonth , 'total' : total  })
        return render(request, 'invoice.html', { 'vm': vm , 'username': username  , 'details': details  } )


@login_required
def profilecopy(request):
    logging.debug('prout')
    username          = request.user.username
    username          = User.objects.get(username=username)
    profiles=Profile.objects.all()
    if request.method == 'POST' and request.is_ajax():
        if request.POST.has_key('newprofile'):
            profile = request.POST['profile']
            profile=Profile.objects.get(name=profile)
            oldcobblerprofile = profile.cobblerprofile
            oldgroups = profile.groups.all()
            newprofilename = request.POST['newprofile']
            exist=Profile.objects.filter(name=newprofilename)
            if exist:
                return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>profile allready existing</div>")
            profile.pk = None
            profile.save()
            profileid = profile.id
            newprofile=Profile.objects.get(id=profileid)
            newprofile.name = newprofilename
            newprofile.cobblerprofile = oldcobblerprofile
            newprofile.groups = oldgroups
            newprofile.save()
            return HttpResponse("<div class='alert alert-success' ><button type='button' class='close' data-dismiss='alert'>&times;</button>profile successfully copied. edit it <a href=%s/admin/portal/profile/%s>here</a></div>" % (baseurl, profileid ) )
        else:
            profile = request.POST['profile']
            profile=Profile.objects.get(name=profile)
            cobblerprofile=profile.name
            if profile.cobblerprofile:
                cobblerprofile=profile.cobblerprofile
            return HttpResponse("<div class='alert alert-success' ><button type='button' class='close' data-dismiss='alert'>&times;</button>Cobbler Profile: %s<p><p>Datacenter: %s<p>Cluster: %s<p>Number of cpus: %s<p>Memory: %sMo<p>Guestid: %s<p>Disksize first disk : %sGb<p>Number of network interfaces: %s<p>Foreman Enabled: %s<p>Cobbler Enabled:%s<p>Isos List Enabled: %s<p>Virtual Provider: %s<p>Physical Provider: %s<p></div>" % (cobblerprofile,profile.datacenter,profile.clu,profile.numcpu,profile.memory,profile.guestid,profile.disksize1,profile.numinterfaces,profile.foreman,profile.cobbler,profile.iso,profile.virtualprovider,profile.physicalprovider ))
    elif username.is_staff:
        profiles = Profile.objects.all()
        if not profiles:
            information = { 'title':'Missing elements' , 'details':'Create profiles first...' }
            return render(request, 'information.html', { 'information' : information , 'username': username } )
        else:
            return render(request, 'profilecopy.html', { 'profiles': profiles , 'username': username } )


@login_required
def findvm(request):
    logging.debug("prout")
    if request.method == 'POST' and request.POST.has_key('name') and request.POST.has_key('profile') and request.POST.has_key('physical'):
        profile = request.POST.get('profile')
        name = request.POST.get('name')
        physical = request.POST.get('physical')
        profile = Profile.objects.get(id=profile)
        results = [profile.numinterfaces]
        if physical == 'false':
            physical = False
        else:
            physical = True
        if physical:
            physicalprovider = profile.physicalprovider
            if physicalprovider.type=='ilo':
                ipilo = request.POST.get('ip')
                ilo=Ilo(ipilo,physicalprovider.user,physicalprovider.password)
                macs = ilo.getmacs()
            elif physicalprovider.type=='oa':
                ipilo = request.POST.get('ip')
                oa=Oa(ipilo,physicalprovider.user,physicalprovider.password)
                bladeid = oa.getid(name)
                macs = oa.getmacs(bladeid)
        else:
            virtualprovider = profile.virtualprovider
            if virtualprovider.type =='ovirt':
                ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
                macs = ovirt.getmacs(name)
                ovirt.close()
            if virtualprovider.type =='kvirt':
                kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
                macs = kvirt.getmacs(name)
                kvirt.close()
            if virtualprovider.type =='vsphere':
                macscommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s %s" % (settings.PWD,'getmacs', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu, name)
                macscommand = os.popen(macscommand).read()
                macs = ast.literal_eval(macscommand)
            if virtualprovider.type =='vsphere2':
		vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
                macs = vsphere.getmacs(name)
                vsphere.close()
        results.append(macs)
        if physical:
            physicalprovider = profile.physicalprovider
            results.append(physicalprovider.type)
        results = json.dumps(results)
        return HttpResponse(results,mimetype='application/json')

@login_required
def quickvms(request):
    name              = request.POST.get('name')
    default           = getdefault()
    username          = User.objects.get(username=request.user.username)
    vms               = VM.objects.filter(name__icontains=name, createdby=username)
    if len(vms) > 0:
        return render(request, 'quickvms.html', { 'vms': vms, 'username': username, 'default' : default  } )
    else:
        return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>No VM found</div>")

@login_required
def templateprofile(request):
    username          = User.objects.get(username=request.user.username)
    #vproviders = VirtualProvider.objects.filter(Q(type='ovirt')|Q(type='vsphere')|Q(type='kvirt')|Q(type='vsphere2'))
    #return render(request, 'profiletemplate.html', { 'vproviders' : vproviders, 'username': username } )
    if not username.is_staff:
        information = { 'title':'Nuages Restricted Information' , 'details':'Restricted access,sorry....' }
        return render(request, 'information.html', { 'information' : information } )
    if request.method == 'POST' and request.is_ajax():
        templates = ['aa', 'bb', 'cc']
        return render(request, 'templateprofile.html', { 'templates': templates, 'username': username  } )
    else:
        vproviders = VirtualProvider.objects.filter(Q(type='ovirt')|Q(type='vsphere')|Q(type='kvirt')|Q(type='vsphere2'))
        return render(request, 'templateprofile.html', { 'vproviders' : vproviders, 'username': username } )

@login_required
def templateslist(request):
    username          = User.objects.get(username=request.user.username)
    virtualprovider   = request.POST.get('virtualprovider')
    virtualprovider   = VirtualProvider.objects.get(name=virtualprovider)
    if virtualprovider.type == 'ovirt':
        ovirt     = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
        results   = ovirt.gettemplates()
        ovirt.close()
        results = json.dumps(results)
        return HttpResponse(results, mimetype='application/json')
    elif virtualprovider.type == 'kvirt':
        kvirt   = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
        results = kvirt.gettemplates()
        kvirt.close()
        results = json.dumps(results)
        return HttpResponse(results, mimetype='application/json')
    elif virtualprovider.type == 'vsphere':
        gettemplatescommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s" % (settings.PWD, 'gettemplates', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu)
        gettemplatescommand = os.popen(gettemplatescommand).read()
        results = ast.literal_eval(gettemplatescommand)
        results = json.dumps(results)
        return HttpResponse(results, mimetype='application/json')
    elif virtualprovider.type == 'vsphere2':
	vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
        results = vsphere.gettemplates()
        vsphere.close()
        results = json.dumps(results)
        return HttpResponse(results, mimetype='application/json')

@login_required
def createtemplateprofile(request):
    username          = User.objects.get(username=request.user.username)
    if not username.is_staff:
        information = { 'title':'Nuages Restricted Information' , 'details':'Restricted access,sorry....' }
        return render(request, 'information.html', { 'information' : information } )
    elif request.method == 'POST':
        name              = request.POST.get('name')
        template          = request.POST.get('template')
        virtualprovider   = request.POST.get('virtualprovider')
        virtualprovider   = VirtualProvider.objects.get(name=virtualprovider)
        newprofile = Profile(name=name, template=template, clu=virtualprovider.clu , datacenter=virtualprovider.datacenter, guestid='rhel_6x64', virtualprovider=virtualprovider )
        newprofile.save()
        profileid = newprofile.id
        return HttpResponse("profile successfully created from template. edit it <a href=%s/admin/portal/profile/%s>here</a></div>" % (baseurl, profileid ) )

def afterbuild(request,name):
    try:
        vm = VM.objects.get(name=name)
        afterbuild = vm.profile.hookafterbuild
        if afterbuild:
            env = os.environ
            env['vm_name'], env['vm_storagedomain'], env['vm_physicalprovider'], env['vm_virtualprovider'], env['vm_physical'], env['vm_cobblerprovider'], env['vm_foremanprovider'], env['vm_profile'], env['vm_ip1'], env['vm_mac1'], env['vm_ip2'], env['vm_mac2'], env['vm_ip3'], env['vm_mac3'], env['vm_ip4'], env['vm_mac4'], env['vm_ipilo'], env['vm_ipoa'], env['vm_iso'], env['vm_hostgroup'], env['vm_puppetclasses'], env['vm_parameters'], env['vm_createdby'], env['vm_createdwhen'], env['vm_price'], env['vm_unmanaged'], env['vm_status'], env['vm_create'] = vm.name, nonone(vm.storagedomain), nonone(vm.profile.physicalprovider), nonone(vm.profile.virtualprovider), nonone(vm.physical), nonone(vm.profile.cobblerprovider), nonone(vm.profile.foremanprovider), nonone(vm.profile), nonone(vm.ip1), nonone(vm.mac1), nonone(vm.ip2), nonone(vm.mac2), nonone(vm.ip3), nonone(vm.mac3), nonone(vm.ip4), nonone(vm.mac4), nonone(vm.ipilo), nonone(vm.ipoa), nonone(vm.iso), nonone(vm.hostgroup), nonone(vm.puppetclasses), nonone(vm.parameters), nonone(vm.createdby), nonone(vm.createdwhen), nonone(vm.price), nonone(vm.unmanaged), nonone(vm.status), nonone(vm.create)
            env['vm_mail'] = vm.createdby.email
            scriptpath  = "%s/%s" % (hooks, afterbuild.name)
            interpreter = afterbuild.type
            if not os.path.exists(scriptpath):
                content = afterbuild.content
                f = open(scriptpath)
                f.write(content)
                f.close()
            subprocess.Popen("%s %s" % (interpreter, scriptpath), stdout=subprocess.PIPE, shell=True, env=env).stdout.read()
        return HttpResponse('OK')
    except:
        return HttpResponse('KO')

@login_required
def customformforeman(request):
    logging.debug('prout')
    if os.path.exists('/tmp/customtypes.py.lock' ):
        response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>customtypes  currently edited by another user</div>"
        return HttpResponse(response)
    else:
        allclasses = {}    
        for foremanprovider in ForemanProvider.objects.all():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((foremanprovider.host, foremanprovider.port))
                available = True
            except socket.error:
                available=False
            if available:
                foremanhost, foremanport, foremansecure, foremanuser, foremanpassword, foremanenv = foremanprovider.host, foremanprovider.port, foremanprovider.secure, foremanprovider.user, foremanprovider.password , foremanprovider.envid
                foreman= Foreman(host=foremanhost, port=foremanport,user=foremanuser, password=foremanpassword, secure=foremansecure)
                classes = foreman.classes(foremanenv)
                for foremanclass in classes:
                    if not foremanclass in allclasses.keys():
                        classinfo = foreman.classinfo(foremanclass) 
                        allclasses[foremanclass] = classinfo
        if len(allclasses) == 0:
            response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>no classes found, not doing anything</div>"
            return HttpResponse(response)
        if os.path.exists("%s/portal/customtypes.py" % settings.PWD):
            os.remove("%s/portal/customtypes.py" % settings.PWD )
        f=open("%s/portal/customtypes.py" % settings.PWD , 'w')
        f.write("from django import forms\n")
        for puppetclass in sorted(allclasses):
            f.write("class %s(forms.Form):\n" % puppetclass.replace('::', '__'))
            parameters = allclasses[puppetclass]
            if len(parameters) == 0:
                f.write("\tpass\n")
                continue
            for parameter in sorted(parameters):
                default, required = parameters[parameter][0], parameters[parameter][1]
                if required:
                    #TO FIX WITH CORRECT WAY TO SAY FIELD IS REQUIRED
                    required= ''
                else:    
                    required = ''
                if 'join' in dir(default):
                    fieldtype = 'CharField'
                elif 'real' in dir(default):    
                    fieldtype = 'IntegerField'
                else:    
                    fieldtype = 'ChoiceField'
                if fieldtype == "IntegerField" and default != None:
                    f.write("\t%s\t= forms.%s(initial=%s%s)\n" % (parameter, fieldtype, int(default), required ) )
                elif fieldtype == "CharField" and default != None:
                    f.write("\t%s\t= forms.%s(initial=\"%s\"%s)\n" % (parameter, fieldtype, default, required ) )
                elif fieldtype == "ChoiceField" and default != None:
                    choices=''
                    for choice in default:
                        if choices == '':
                            choices = "('%s', '%s')" % (choice,choice)
                        else:
                            choices = choices+",('%s', '%s')" % (choice, choice)
                    f.write("\t%s\t= forms.%s(choices=(%s)%s)\n" % (parameter, fieldtype, choices, required ) )
                else:
                    if len(required) >0:
                        #TO FIX WITH CORRECT WAY TO SAY FIELD IS REQUIRED
                        required= ''
                    f.write("\t%s\t= forms.%s(%s)\n" % (parameter, fieldtype, required) )
        f.close()
        responselist = ' '.join(allclasses.keys())
        response = "<div class='alert alert-success'><button type='button' class='close' data-dismiss='alert'>&times;</button>Customforms populated from foreman providers and with those classes:<p> %s</div>" % responselist 
        return HttpResponse(response)

@login_required
def customformcobbler(request):
    logging.debug('prout')
    if os.path.exists('/tmp/customtypes.py.lock' ):
        response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>customtypes  currently edited by another user</div>"
        return HttpResponse(response)
    else:
        allclasses = {}    
        for cobblerprovider in CobblerProvider.objects.all():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((cobblerprovider.host, COBBLERPORT))
                available = True
            except socket.error:
                available=False
            if available:
                cobblerhost, cobbleruser, cobblerpassword = cobblerprovider.host, cobblerprovider.user, cobblerprovider.password 
                cobbler= Cobbler(cobblerhost=cobblerhost, cobbleruser=cobbleruser, cobblerpassword=cobblerpassword)
                allclasses = cobbler.classes()
        if len(allclasses) == 0:
            response = "<div class='alert alert-error'><button type='button' class='close' data-dismiss='alert'>&times;</button>no classes found, not doing anything</div>"
            return HttpResponse(response)
        if os.path.exists("%s/portal/customtypes.py" % settings.PWD):
            os.remove("%s/portal/customtypes.py" % settings.PWD )
        f=open("%s/portal/customtypes.py" % settings.PWD , 'w')
        f.write("from django import forms\n")
        for puppetclass in sorted(allclasses):
            f.write("class %s(forms.Form):\n" % puppetclass.replace('::', '__'))
            parameters = allclasses[puppetclass]
            if len(parameters) == 0:
                f.write("\tpass\n")
                continue
            for parameter in sorted(parameters):
                default, required = parameters[parameter][0], parameters[parameter][1]
                if required:
                    #TO FIX WITH CORRECT WAY TO SAY FIELD IS REQUIRED
                    required= ''
                else:    
                    required = ''
                if 'join' in dir(default):
                    fieldtype = 'CharField'
                elif 'real' in dir(default):    
                    fieldtype = 'IntegerField'
                else:    
                    fieldtype = 'ChoiceField'
                if fieldtype == "IntegerField" and default != None:
                    f.write("\t%s\t= forms.%s(initial=%s%s)\n" % (parameter, fieldtype, int(default), required ) )
                elif fieldtype == "CharField" and default != None:
                    f.write("\t%s\t= forms.%s(initial=\"%s\"%s)\n" % (parameter, fieldtype, default, required ) )
                elif fieldtype == "ChoiceField" and default != None:
                    choices=''
                    for choice in default:
                        if choices == '':
                            choices = "('%s', '%s')" % (choice,choice)
                        else:
                            choices = choices+",('%s', '%s')" % (choice, choice)
                    f.write("\t%s\t= forms.%s(choices=(%s)%s)\n" % (parameter, fieldtype, choices, required ) )
                else:
                    if len(required) >0:
                        #TO FIX WITH CORRECT WAY TO SAY FIELD IS REQUIRED
                        required= ''
                    f.write("\t%s\t= forms.%s(%s)\n" % (parameter, fieldtype, required) )
        f.close()
        responselist = ' '.join(allclasses.keys())
        response = "<div class='alert alert-success'><button type='button' class='close' data-dismiss='alert'>&times;</button>Customforms populated from Cobbler providers and with those classes:<p> %s</div>" % responselist 
        return HttpResponse(response)

@login_required
def stacks(request):
    username          = request.user.username
    username          = User.objects.filter(username=username)[0]
    if request.method == 'POST':
        stackname         = request.POST.get('name')
        numvms            = int(request.POST.get('numvms'))
        name1             = request.POST.get('name1')
        name2             = request.POST.get('name2')
        name3             = request.POST.get('name3')
        name4             = request.POST.get('name4')
        name5             = request.POST.get('name5')
        name6             = request.POST.get('name6')
        name7             = request.POST.get('name7')
        name8             = request.POST.get('name8')
        name9             = request.POST.get('name9')
        name10            = request.POST.get('name10')
        profile1          = request.POST.get('profile1')
        profile2          = request.POST.get('profile2')
        profile3          = request.POST.get('profile3')
        profile4          = request.POST.get('profile4')
        profile5          = request.POST.get('profile5')
        profile6          = request.POST.get('profile6')
        profile7          = request.POST.get('profile7')
        profile8          = request.POST.get('profile8')
        profile9          = request.POST.get('profile9')
        profile10         = request.POST.get('profile10')
        hostgroup1        = request.POST.get('hostgroup1')
        hostgroup2        = request.POST.get('hostgroup2')
        hostgroup3        = request.POST.get('hostgroup3')
        hostgroup4        = request.POST.get('hostgroup4')
        hostgroup5        = request.POST.get('hostgroup5')
        hostgroup6        = request.POST.get('hostgroup6')
        hostgroup7        = request.POST.get('hostgroup7')
        hostgroup8        = request.POST.get('hostgroup8')
        hostgroup9        = request.POST.get('hostgroup9')
        hostgroup10       = request.POST.get('hostgroup10')
        profiles          = { 1 : profile1 , 2 : profile2, 3 : profile3, 4 : profile4 , 5 : profile5, 6 : profile6, 7 : profile7 , 8 : profile8, 9 : profile9, 10: profile10 }
        hostgroups        = { 1 : hostgroup1 , 2 : hostgroup2, 3 : hostgroup3, 4 : hostgroup4 , 5 : hostgroup5, 6 : hostgroup6, 7 : hostgroup7 , 8 : hostgroup8, 9 : hostgroup9, 10: hostgroup10 }
        names             = { 1 : name1 , 2 : name2, 3 : name3, 4 : name4 , 5 : name5, 6 : name6, 7 : name7 , 8 : name8, 9 : name9, 10: name10 }
        parameters        = request.POST.get('parameters')
        stack             = Stack(name=stackname, numvms=numvms, createdby=username)
        stack.save()
        failure = False
        for num in range(1,numvms+1):
            name       = names[num]
            hostgroup  = hostgroups[num]
            if hostgroup == '':
                hostgroup = None
            profile    = profiles[num]
            profilevms = profiles.values().count(profile)
            profile    = Profile.objects.get(name=profile)
            if profile.maxvms:
                currentvms = len(VM.objects.filter(profile=profile))
                if currentvms + profilevms > profile.maxvms:
                    return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>Exceeded maximum vms for this profile<p</div>")
            virtualprovider, cobblerprovider, foremanprovider, ipamprovider = profile.virtualprovider, profile.cobblerprovider, profile.foremanprovider, profile.ipamprovider
            disksize1, disksize2, numinterfaces, requireip, cobbler, foreman = profile.disksize1, profile.disksize2, profile.numinterfaces, profile.requireip, profile.cobbler, profile.foreman
            # get best storage domain
            datacenter = profile.datacenter
            if virtualprovider.type == 'ovirt':
                ovirt = Ovirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,virtualprovider.password,virtualprovider.ssl)
                storagedomain = ovirt.beststorage(datacenter)
                ovirt.close()
            elif virtualprovider.type == 'kvirt':
                kvirt = Kvirt(virtualprovider.host,virtualprovider.port,virtualprovider.user,protocol='ssh')
                storagedomain = kvirt.beststorage()
                kvirt.close()
            elif virtualprovider.type == 'vsphere':
                beststoragecommand = "/usr/bin/jython %s/portal/vsphere.py %s %s %s %s %s %s" % (settings.PWD,'beststorage', virtualprovider.host, virtualprovider.user, virtualprovider.password , virtualprovider.datacenter, virtualprovider.clu)
                bestds = os.popen(beststoragecommand).read()
                storagedomain = bestds.strip()
            elif virtualprovider.type == 'vsphere2':
		vsphere   = Vsphere(virtualprovider.host,virtualprovider.user,virtualprovider.password,virtualprovider.datacenter, virtualprovider.clu)
                storagedomain = vsphere.beststorage()
                vsphere.close()
            if name == '' and not ipamprovider:
                    failure   = True
            #MAKE SURE VM DOESNT ALLREADY EXISTS IN DB WITH THIS SAME VIRTUALPROVIDER
            vms = VM.objects.filter(name=name).filter(profile=profile)
            if len(vms) > 0:
                return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>VM %s allready exists</div>" % name)
            if not virtualprovider.type == 'fake' and not profile.autostorage:
                storageresult=checkstorage(profilevms,virtualprovider,disksize1,disksize2,storagedomain)
                if storageresult != 'OK':
                    return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>%s</div>" % storageresult )
            puppetclasses = None
            parameters = None
            newvm = VM(name=name, storagedomain=storagedomain, profile=profile, createdby=username, hostgroup=hostgroup)
            success = newvm.save()
            if success == 'OK':
                stack.vms.add(newvm)
            else:    
                failure   = True
                break
        if not failure:
            return HttpResponse("<div class='alert alert-success' ><button type='button' class='close' data-dismiss='alert'>&times;</button>Stack %s successfully created!</div>" % stackname )
        else:
            # WE SHOULD DELETE ALL VMS OF THE STACK AND THE STACK
            stack.delete()
            return HttpResponse("<div class='alert alert-error' ><button type='button' class='close' data-dismiss='alert'>&times;</button>Stack %s not createdbecause %s !</div>" % (stackname,success) )
    elif username.is_staff:
        profiles = Profile.objects.all()
        if not profiles:
            information = { 'title':'Missing elements' , 'details':'Create profiles first...' }
            return render(request, 'information.html', { 'information' : information , 'username': username } )
        else:
            return render(request, 'stacks.html', { 'username': username, 'profiles': profiles  } )
    else:
        usergroups=[]
        for g in groups.values():
            usergroups.append(g['id'])
        if len(usergroups) == 0:
            query = Q(groups=None)
        else:
            query = Q(groups=None)|Q(groups=usergroups[0])
            for group in usergroups[1:]:
                query=query|Q(groups=group)
        query=Profile.objects.filter(query)
        if not query:
            information = { 'title':'Missing elements' , 'details':'Create profiles first...' }
            return render(request, 'information.html', { 'information' : information } )
        return render(request, 'stacks.html', { 'username': username, 'profiles': profiles  } )

@login_required
def yourstacks(request):
    #ajax = False
    #if request.is_ajax():
    #    ajax = True
    username          = request.user.username
    username          = User.objects.get(username=username)
    usergroups        = username.groups
    query             = Q(createdby=username)
    allusers          = User.objects.all()
    for g in usergroups.all():
        for u in allusers:
            if u.username == username.username:
                continue
            if g in u.groups.all():
                query=query|Q(createdby=u)
    stacks = Stack.objects.filter(query)
    return render(request, 'yourstacks.html', { 'stacks': stacks, 'username': username  } )

@login_required
def stopstack(request):
    if request.method == 'POST':
        stackname = request.POST.get('name')
        stack     = Stack.objects.get(name=stackname)
        vms       = stack.stop()
        results   = "stack %s stopped with the following vms<p>" % stackname
        for vm in vms:
            results =  "%s%s<p>" % ( results, vm)
        return HttpResponse(results)

@login_required
def startstack(request):
    if request.method == 'POST':
        stackname = request.POST.get('name')
        stack     = Stack.objects.get(name=stackname)
        vms       = stack.start()
        results   = "stack %s started with the following vms<p>" % stackname
        for name in sorted(vms):
            url        = vms[name]
            consoleurl = "<a href='%s'>%s</a><p>" % ( url, name )
            results    =  "%s%s" % ( results, consoleurl)
        return HttpResponse(results)

@login_required
def killstack(request):
    if request.method == 'POST':
        stackname = request.POST.get('name')
        stack     = Stack.objects.get(name=stackname)
        vms       = stack.kill()
        results   = "stack %s killed along with the following vms<p>" % stackname
        for name in vms:
            results =  "%s%s<p>" % ( results, name)
        stack.delete()
        return HttpResponse(results)

@login_required
def showstack(request):
    logging.debug("prout")
    if request.method == 'POST':
        stackname = request.POST.get('name')
        stack     = Stack.objects.get(name=stackname)
        results   = "stack %s contains the following vms<p>" % stackname
        vms       = stack.show()
        for name in sorted(vms):
            url        = vms[name]
            consoleurl = "<a href='%s'>%s</a><p>" % ( url, name )
            results    =  "%s%s" % ( results, consoleurl)
        return HttpResponse(results)
