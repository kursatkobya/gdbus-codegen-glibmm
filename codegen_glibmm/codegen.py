# -*- Mode: Python -*-

# GDBus - GLib D-Bus Library
#
# Copyright (C) 2008-2011 Red Hat, Inc.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General
# Public License along with this library; if not, see <http://www.gnu.org/licenses/>.
#
# Author: David Zeuthen   <davidz@redhat.com>
#  (2014) Jonatan Palsson <jonatan.palsson@pelagicore.com>

import sys, os

from jinja2 import Environment, FileSystemLoader

from textwrap import dedent

from . import config
from . import utils
from . import dbustypes

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------------------------------

SIGNAL_MAX_PARAM = 10

class CodeGenerator:
    def __init__(self, ifaces, namespace, interface_prefix, node_xmls, proxy_h, proxy_cpp, stub_cpp, stub_h, common_cpp, common_h):
        self.ifaces = ifaces
        self.proxy_h = proxy_h
        self.proxy_cpp = proxy_cpp
        self.stub_h = stub_h
        self.stub_cpp = stub_cpp
        self.common_h = common_h
        self.common_cpp = common_cpp
        self.node_xmls = node_xmls

    def emit (self, dest, text, newline = True):
        """ Emit code to the specified file
            @param newline boolean indicating whether to append a newline to
                           generated code
        """
        dest.write (text)
        if newline:
            dest.write ("\n")

    def emit_h_p (self, text, newline = True):
        """ Emit code to proxy header file
            @param newline boolean indicating whether to append a newline to
                           generated code
        """
        self.emit(self.proxy_h, text, newline)

    def emit_cpp_p (self, text, newline = True):
        """ Emit code to proxy cpp file
            @param newline boolean indicating whether to append a newline to
                           generated code
        """
        self.emit(self.proxy_cpp, text, newline)

    def emit_h_s (self, text, newline = True):
        """ Emit code to stub header file
            @param newline boolean indicating whether to append a newline to
                           generated code
        """
        self.emit(self.stub_h, text, newline)

    def emit_cpp_s (self, text, newline = True):
        """ Emit code to stub cpp file
            @param newline boolean indicating whether to append a newline to
                           generated code
        """
        self.emit(self.stub_cpp, text, newline)

    def emit_h_common (self, text, newline = True):
        """ Emit code to common header file
            @param newline boolean indicating whether to append a newline to
                           generated code
        """
        self.emit(self.common_h, text, newline)

    def emit_cpp_common (self, text, newline = True):
        """ Emit code to common cpp file
            @param newline boolean indicating whether to append a newline to
                           generated code
        """
        self.emit(self.common_cpp, text, newline)

    def generate_proxy_header(self):
        """ Generate types and classes required by the proxy. This will
        generate a complete class declaration, which is implemented in the
        corresponding cpp file
        """
        h = self.j2_env.get_template('proxy.h.templ').render(
                interfaces=self.ifaces,
                common_h_name=self.common_h.name)
        self.emit_h_p(h)

    def generate_proxy_impl(self):
        """ Generate implementation code for the proxy objects.
        """
        h = self.j2_env.get_template('proxy.cpp.templ').render(
                interfaces=self.ifaces,
                program_version=config.VERSION,
                proxy_h_name=self.proxy_h.name)
        self.emit_cpp_p(h)

    def generate_stub_introspection(self):
        """ Generate introspection XML for all introspection XML files """
        for i in range(0, len(self.node_xmls)):
            node_xml = self.node_xmls[i]

            # This will encode the XML introspection data as raw bytes. This is
            # to avoid any formatting issues when embedding the introspection
            # data in the stub file.
            self.emit_cpp_s ("static const char interfaceXml%d[] = R\"XML_DELIMITER(" % i, False)
            for char in node_xml:
                self.emit_cpp_s (chr(char), False)
            self.emit_cpp_s (")XML_DELIMITER\";")

    def generate_stub_intro(self):
        """ Generate introduction for stub cpp file """
        self.emit_cpp_s ('#include "%s"' % self.stub_h.name)

    def generate_stub_header(self):
        """ Generate types and classes for the stub. This will generate the
        complete class needed for implementing the stub. The code is placed in
        the header file for the stub.
        """
        h = self.j2_env.get_template('stub.h.templ').render(
                interfaces=self.ifaces,
                common_h_name=self.common_h.name)
        self.emit_h_s(h)

    def define_types_stub_creation(self, i):
        # Constructor
        self.emit_cpp_s(dedent('''
        {i.cpp_namespace_name}::{i.cpp_class_name} () : connectionId(0), registeredId(0), m_interfaceName("{i.name}") {{
        ''').format(**locals()))
        for s in i.signals:
            # Sigc does not allow an infinite number of parameters for signals.
            # The maximum number of signals is specified in SIGNAL_MAX_PARAM. A
            # warning is issued if this is exceeded, and no signal handler uis
            # generated.
            if (len(s.args) > SIGNAL_MAX_PARAM):
                print("WARNING: signal %s has too many parameters, skipping" % s.name)
                continue
            self.emit_cpp_s("    {s.name}_signal.connect(sigc::mem_fun(this, &{i.cpp_class_name}::{s.name}_emitter));".format(**locals()))
        #TODO: This code will only fetch introspection data for interfaces
        # contained in the first interfaceXml variable. We need to check which
        # interfaceXml variable contains our XML, and use the correct one
        # instead. This code will break if there are several introspection XML
        # files specified.
        self.emit_cpp_s(dedent('''
        }}

        {i.cpp_namespace_name}::~{i.cpp_class_name}()
        {{
        }}

        guint {i.cpp_namespace_name}::register_object(
            const Glib::RefPtr<Gio::DBus::Connection> &connection,
            const Glib::ustring &object_path)
        {{
            if (!m_objectPath.empty() && m_objectPath != object_path) {{
                g_warning("Cannot register the same object twice!");

                return 0;
            }}
            try {{
                    introspection_data = Gio::DBus::NodeInfo::create_for_xml(interfaceXml0);
            }} catch(const Glib::Error& ex) {{
                    g_warning("Unable to create introspection data: ");
                    g_warning("%s\\n", ex.what().c_str());
            }}
            Gio::DBus::InterfaceVTable *interface_vtable =
                new Gio::DBus::InterfaceVTable(
                    sigc::mem_fun(this, &{i.cpp_class_name}::on_method_call),
                    sigc::mem_fun(this, &{i.cpp_class_name}::on_interface_get_property),
                    sigc::mem_fun(this, &{i.cpp_class_name}::on_interface_set_property));
            guint id = 0;
            try {{
                id = connection->register_object(object_path,
                    introspection_data->lookup_interface("{i.name}"),
                    *interface_vtable);
                m_connection = connection;
                m_objectPath = object_path;
            }}
            catch(const Glib::Error &ex) {{
                g_warning("Registration of object failed");
            }}
            return id;
        }}

        void {i.cpp_namespace_name}::connect (
            Gio::DBus::BusType busType,
            std::string name)
        {{
            connectionId = Gio::DBus::own_name(busType,
                                               name,
                                               sigc::mem_fun(this, &{i.cpp_class_name}::on_bus_acquired),
                                               sigc::mem_fun(this, &{i.cpp_class_name}::on_name_acquired),
                                               sigc::mem_fun(this, &{i.cpp_class_name}::on_name_lost));
        }}''').format(**locals()))


    def define_types_method_handlers_stub(self, i):
        """ Generate code for handling and dispatching method calls in the
        stub. This code will trigger the correct user-defined function with
        parameter types converted to std:: c++ types.
        @param Interface i is the interface to generate method handlers for
        """
        self.emit_cpp_s(dedent('''
        void {i.cpp_namespace_name}::on_method_call(const Glib::RefPtr<Gio::DBus::Connection>& /* connection */,
                           const Glib::ustring& /* sender */,
                           const Glib::ustring& /* object_path */,
                           const Glib::ustring& /* interface_name */,
                           const Glib::ustring& method_name,
                           const Glib::VariantContainerBase& parameters,
                           const Glib::RefPtr<Gio::DBus::MethodInvocation>& invocation)
        {{
        ''').format(**locals()))
        for m in i.methods:
            #TODO: Make more thorough checks here. Method name is not enough.
            self.emit_cpp_s("    if (method_name.compare(\"%s\") == 0) {" % m.name)
            for ai in range(len(m.in_args)):
                a = m.in_args[ai]
                if a.templated:
                    # Variants are deconstructed differently than the other types
                    self.emit_cpp_s("        Glib::VariantContainerBase containerBase = parameters;")
                    self.emit_cpp_s("        GVariant *output%s;" % (ai))
                    self.emit_cpp_s('        g_variant_get_child(containerBase.gobj(), %s, "v", &output%s);' % (ai, ai))
                    self.emit_cpp_s("        Glib::VariantBase p_%s;" % (a.name))
                    self.emit_cpp_s("        p_%s = Glib::VariantBase(output%s);" % (a.name, ai))
                    self.emit_cpp_s("")
                else:
                    self.emit_cpp_s("        Glib::Variant<%s > base_%s;" % (a.variant_type, a.name))
                    self.emit_cpp_s("        parameters.get_child(base_%s, %d);" % (a.name, ai))
                    self.emit_cpp_s("        %s p_%s;" % (a.variant_type, a.name))
                    self.emit_cpp_s("        p_%s = base_%s.get();" % (a.name, a.name))
                    self.emit_cpp_s("")
            self.emit_cpp_s("        %s(" % m.name)
            for a in m.in_args:
                self.emit_cpp_s("            %s(p_%s)," % (a.cpptype_get_cast, a.name))
            self.emit_cpp_s("            {i.cpp_class_name}MessageHelper(invocation));".format(**locals()))
            self.emit_cpp_s("    }")
        self.emit_cpp_s("    }")

    def define_types_property_get_handlers_stub(self, i):
        object_path = "/" + i.name.replace(".", "/")

        self.emit_cpp_s(dedent('''
        void {i.cpp_namespace_name}::on_interface_get_property(Glib::VariantBase& property,
                                               const Glib::RefPtr<Gio::DBus::Connection>& connection,
                                               const Glib::ustring& sender,
                                               const Glib::ustring& object_path,
                                               const Glib::ustring& interface_name,
                                               const Glib::ustring& property_name) {{
        ''').format(**locals()))

        for p in i.properties:
            if p.readable:
                self.emit_cpp_s(dedent('''
                    if (property_name.compare("{p.name}") == 0) {{
                        property = Glib::Variant<{p.variant_type} >::create({p.cpptype_to_dbus}({p.name}_get()));
                    }}
                ''').format(**locals()))

        self.emit_cpp_s("}")

    def define_types_property_set_handlers_stub(self, i):
        object_path = "/" + i.name.replace(".", "/")
        self.emit_cpp_s(dedent('''
        bool {i.cpp_namespace_name}::on_interface_set_property(
               const Glib::RefPtr<Gio::DBus::Connection>& connection,
               const Glib::ustring& sender,
               const Glib::ustring& object_path,
               const Glib::ustring& interface_name,
               const Glib::ustring& property_name,
               const Glib::VariantBase& value) {{
        ''').format(**locals()))

        for p in i.properties:
            self.emit_cpp_s(dedent('''
                if (property_name.compare("{p.name}") == 0) {{
                    try {{
                        Glib::Variant<{p.variant_type} > castValue = Glib::VariantBase::cast_dynamic<Glib::Variant<{p.variant_type} > >(value);
                        {p.cpptype_out} val;''').format(**locals()))
            self.emit_cpp_s(dedent('''
                        val = {p.cpptype_get_cast}(castValue.get());''').format(**locals()))
            self.emit_cpp_s('''        {p.name}_set(val);'''.format(**locals()))
            self.emit_cpp_s(dedent('''
                    }} catch (std::bad_cast e) {{
                        g_warning ("Bad cast when casting {p.name}");
                    }}
                }}
            ''').format(**locals()))

        self.emit_cpp_s(dedent('''
            return true;
        }}
        ''').format(**locals()))

    def define_types_signal_emitters_stub(self, i):
        object_path = "/" + i.name.replace(".", "/")

        for s in i.signals:
            # Sigc does not allow an infinite number of parameters for signals.
            # The maximum number of signals is specified in SIGNAL_MAX_PARAM. A
            # warning is issued if this is exceeded, and no signal handler uis
            # generated.
            if (len(s.args) > SIGNAL_MAX_PARAM):
                print("WARNING: signal %s has too many parameters, skipping" % s.name)
                continue
            args = []

            for a in s.args:
                args.append(a.cpptype_out + " " + a.name)

            argsStr = ", ".join(args)
            self.emit_cpp_s(dedent('''void {i.cpp_namespace_name}::{s.name}_emitter({argsStr}) {{
            std::vector<Glib::VariantBase> paramsList;''').format(**locals()))

            for a in s.args:
                self.emit_cpp_s(dedent('''
                paramsList.push_back(Glib::Variant<{a.variant_type} >::create({a.cpptype_to_dbus}({a.name})));;
                ''').format(**locals()))

            self.emit_cpp_s(dedent('''      m_connection->emit_signal(
                    "{object_path}",
                    "{s.iface_name}",
                    "{s.name}",
                    Glib::ustring(),
                    Glib::Variant<std::vector<Glib::VariantBase> >::create_tuple(paramsList));
            }}''').format(**locals()))

    def define_types_dbus_callbacks_stub(self, i):
        object_path = "/" + i.name.replace(".", "/")
        self.emit_cpp_s(dedent('''
        void {i.cpp_namespace_name}::on_bus_acquired(const Glib::RefPtr<Gio::DBus::Connection>& connection,
                                 const Glib::ustring& /* name */) {{
            registeredId = register_object(connection,
                                           "{object_path}");
            m_connection = connection;

            return;
        }}
        void {i.cpp_namespace_name}::on_name_acquired(const Glib::RefPtr<Gio::DBus::Connection>& /* connection */,
                              const Glib::ustring& /* name */) {{}}

        void {i.cpp_namespace_name}::on_name_lost(const Glib::RefPtr<Gio::DBus::Connection>& connection,
                          const Glib::ustring& /* name */) {{}}
        ''').format(**locals()))

    def define_types_property_setters_stub(self, i):
        for p in i.properties:
            self.emit_cpp_s(dedent('''
            bool {i.cpp_namespace_name}::{p.name}_set({p.cpptype_in} value) {{
                if ({p.name}_setHandler(value)) {{
                    Glib::Variant<{p.variant_type} > value_get = Glib::Variant<{p.variant_type} >::create({p.cpptype_to_dbus}({p.name}_get()));
                    emitSignal("{p.name}", value_get);
                    return true;
                }}

                return false;
            }}''').format(**locals()))

    def define_types_emit_stub(self, i):
            self.emit_cpp_s(dedent('''
            bool {i.cpp_namespace_name}::emitSignal(const std::string& propName, Glib::VariantBase& value) {{
                std::map<Glib::ustring, Glib::VariantBase> changedProps;
                std::vector<Glib::ustring> changedPropsNoValue;

                changedProps[propName] = value;

                Glib::Variant<std::map<Glib::ustring,  Glib::VariantBase> > changedPropsVar = Glib::Variant<std::map <Glib::ustring, Glib::VariantBase> >::create (changedProps);
                Glib::Variant<std::vector<Glib::ustring> > changedPropsNoValueVar = Glib::Variant<std::vector<Glib::ustring> >::create(changedPropsNoValue);
                std::vector<Glib::VariantBase> ps;
                ps.push_back(Glib::Variant<Glib::ustring>::create(m_interfaceName));
                ps.push_back(changedPropsVar);
                ps.push_back(changedPropsNoValueVar);
                Glib::VariantContainerBase propertiesChangedVariant = Glib::Variant<std::vector<Glib::VariantBase> >::create_tuple(ps);

                m_connection->emit_signal(
                    m_objectPath,
                    "org.freedesktop.DBus.Properties",
                    "PropertiesChanged",
                    Glib::ustring(),
                    propertiesChangedVariant);

                return true;
            }}''').format(**locals()))

    def generate_common(self, interfaces):
        h = self.j2_env.get_template('common.h.templ').render(
                interfaces=interfaces)
        self.emit_h_common(h)

    def initialize_jinja(self):
        self.j2_env = Environment(loader=FileSystemLoader(THIS_DIR + "/templates/"),
                                  trim_blocks=True,
                                  lstrip_blocks=True)
        def is_templated(method):
            for a in method.in_args:
                if a.templated:
                    return True
            return False
        self.j2_env.tests['templated'] = is_templated

        def is_supported_by_sigc(signal):
            return len(signal.args) <= SIGNAL_MAX_PARAM
        self.j2_env.tests['supported_by_sigc'] = is_supported_by_sigc

    def generate(self):
        # Jinja initialization
        self.initialize_jinja()

        # Proxy
        self.generate_proxy_header()
        self.generate_proxy_impl()

        # Stub
        self.generate_stub_header()
        self.generate_stub_introspection()
        self.generate_stub_intro()
        for i in self.ifaces:
            self.define_types_stub_creation(i)
            self.define_types_method_handlers_stub(i)
            self.define_types_property_get_handlers_stub(i)
            self.define_types_property_set_handlers_stub(i)
            self.define_types_signal_emitters_stub(i)
            self.define_types_dbus_callbacks_stub(i)
            self.define_types_property_setters_stub(i)
            self.define_types_emit_stub(i)

        # Common
        self.generate_common(self.ifaces)
