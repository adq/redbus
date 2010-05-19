/*
 * Copyright 2010 Andrew De Quincey -  adq@lidskialf.net
 * This file is part of rEdBus.
 *
 *  rEdBus is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *
 *  rEdBus is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with rEdBus.  If not, see <http://www.gnu.org/licenses/>.
 */

package org.redbus;

import android.app.AlertDialog;
import android.app.ListActivity;
import android.content.DialogInterface;
import android.content.Intent;
import android.database.Cursor;
import android.os.Bundle;
import android.view.ContextMenu;
import android.view.Menu;
import android.view.MenuInflater;
import android.view.MenuItem;
import android.view.View;
import android.view.ContextMenu.ContextMenuInfo;
import android.widget.AdapterView;
import android.widget.EditText;
import android.widget.ListView;
import android.widget.SimpleCursorAdapter;
import android.widget.TextView;

public class StopBookmarksActivity extends ListActivity
{	
	private static final String[] columnNames = new String[] { LocalDBHelper.ID, LocalDBHelper.BOOKMARKS_COL_STOPNAME };
	private static final int[] listViewIds = new int[] { R.id.stopbookmarks_stopcode, R.id.stopbookmarks_name };

	private long bookmarkId = -1;
	private String bookmarkName = null;

	@Override
	public void onCreate(Bundle savedInstanceState) 
	{
        super.onCreate(savedInstanceState);
        setTitle("Bookmarks");
        setContentView(R.layout.stopbookmarks);
        registerForContextMenu(getListView());
	}

	@Override
	protected void onStart() 
	{
		super.onStart();
		
		update();
	}
	
	private void update()
	{
        LocalDBHelper db = new LocalDBHelper(this);
        try {
        	SimpleCursorAdapter oldAdapter = ((SimpleCursorAdapter) getListAdapter());
        	if (oldAdapter != null)
        		oldAdapter.getCursor().close();
	        Cursor listContentsCursor = db.getBookmarks();
	        startManagingCursor(listContentsCursor);
	        setListAdapter(new SimpleCursorAdapter(this, R.layout.stopbookmarks_item, listContentsCursor, columnNames, listViewIds));
        } finally {
        	db.close();
        }
	}

	@Override
	protected void onListItemClick(ListView l, View v, int position, long id) {		
		String stopName = ((TextView) v.findViewById(R.id.stopbookmarks_name)).getText().toString();
		BusTimesActivity.showActivity(this, id, stopName);
	}

	@Override
	public void onCreateContextMenu(ContextMenu menu, View v, ContextMenuInfo menuInfo) {
	    MenuInflater inflater = getMenuInflater();
	    inflater.inflate(R.menu.stopbookmarks_item_menu, menu);	    
	}

	@Override
	public boolean onContextItemSelected(MenuItem item) {
		AdapterView.AdapterContextMenuInfo menuInfo = (AdapterView.AdapterContextMenuInfo) item.getMenuInfo();
		bookmarkId = menuInfo.id;
		bookmarkName = ((TextView) menuInfo.targetView.findViewById(R.id.stopbookmarks_name)).getText().toString();
		
		switch(item.getItemId()) {
		case R.id.stopbookmarks_item_menu_bustimes:
			BusTimesActivity.showActivity(this, bookmarkId, bookmarkName);
			return true;

		case R.id.stopbookmarks_item_menu_showonmap:
			// FIXME: implement
			return true;

		case R.id.stopbookmarks_item_menu_edit:
			final EditText input = new EditText(this);
			input.setText(bookmarkName);

			new AlertDialog.Builder(this)
					.setTitle("Edit bookmark name")
					.setView(input)
					.setPositiveButton(android.R.string.ok,
							new DialogInterface.OnClickListener() {
								public void onClick(DialogInterface dialog, int whichButton) {
			                        LocalDBHelper db = new LocalDBHelper(StopBookmarksActivity.this);
			                        try {
			                        	db.renameBookmark(StopBookmarksActivity.this.bookmarkId, input.getText().toString());
			                        } finally {
			                        	db.close();
			                        }
			                        StopBookmarksActivity.this.update();
								}
							})
					.setNegativeButton(android.R.string.cancel, null)
					.show();
			return true;

		case R.id.stopbookmarks_item_menu_delete:
			new AlertDialog.Builder(this).
				setMessage("Are you sure you want to delete this bookmark?").
				setNegativeButton(android.R.string.cancel, null).
				setPositiveButton(android.R.string.ok, new DialogInterface.OnClickListener() {
                    public void onClick(DialogInterface dialog, int whichButton) {
                        LocalDBHelper db = new LocalDBHelper(StopBookmarksActivity.this);
                        try {
                        	db.deleteBookmark(StopBookmarksActivity.this.bookmarkId);
                        } finally {
                        	db.close();
                        }
                        StopBookmarksActivity.this.update();
                    }
				}).
                show();
			return true;		
		}

		return super.onContextItemSelected(item);
	}
	
	@Override
	public boolean onCreateOptionsMenu(Menu menu) {		
	    MenuInflater inflater = getMenuInflater();
	    inflater.inflate(R.menu.stopbookmarks_menu, menu);
	    return true;
	}
	
	@Override
	public boolean onOptionsItemSelected(MenuItem item) {
		final EditText input = new EditText(this);

		switch(item.getItemId()) {
		case R.id.stopbookmarks_menu_nearby_stops:
			new AlertDialog.Builder(this).
				setMessage("This feature's GUI is under heavy GUI development").
				setPositiveButton(android.R.string.ok, new DialogInterface.OnClickListener() {
	                public void onClick(DialogInterface dialog, int whichButton) {
	        			startActivity(new Intent(StopBookmarksActivity.this, StopMapActivity.class));
	                }
				}).
	            show();
			return true;

		case R.id.stopbookmarks_menu_bustimes:
			new AlertDialog.Builder(this)
				.setTitle("Enter BusStop code to view")
				.setView(input)
				.setPositiveButton(android.R.string.ok,
						new DialogInterface.OnClickListener() {
							public void onClick(DialogInterface dialog, int whichButton) {
								long stopCode = -1;
								try {
									stopCode = Long.parseLong(input.getText().toString());
								} catch (Exception ex) {
									new AlertDialog.Builder(StopBookmarksActivity.this)
											.setTitle("Invalid BusStop code")
											.setMessage("The code was invalid; please try again using only numbers")
											.setPositiveButton(android.R.string.ok, null)
											.show();
									return;
								}
								
								PointTree.BusStopTreeNode busStop = PointTree.getPointTree(StopBookmarksActivity.this).lookupStopByStopCode((int) stopCode);
								if (busStop != null) {
									BusTimesActivity.showActivity(StopBookmarksActivity.this, (int) busStop.getStopCode(), busStop.getStopName());
								} else {
									new AlertDialog.Builder(StopBookmarksActivity.this)
										.setTitle("Invalid BusStop code")
										.setMessage("The code was invalid; please try again")
										.setPositiveButton(android.R.string.ok, null)
										.show();
								}
							}
						})
				.setNegativeButton(android.R.string.cancel, null)
				.show();
			return true;
			
		case R.id.stopbookmarks_menu_addbookmark:
			new AlertDialog.Builder(this)
				.setTitle("Enter BusStop code for bookmark")
				.setView(input)
				.setPositiveButton(android.R.string.ok,
						new DialogInterface.OnClickListener() {
							public void onClick(DialogInterface dialog, int whichButton) {
								long stopCode = -1;
								try {
									stopCode = Long.parseLong(input.getText().toString());
								} catch (Exception ex) {
									new AlertDialog.Builder(StopBookmarksActivity.this)
											.setTitle("Invalid BusStop code")
											.setMessage("The code was invalid; please try again using only numbers")
											.setPositiveButton(android.R.string.ok, null)
											.show();
									return;
								}
								
								PointTree.BusStopTreeNode busStop = PointTree.getPointTree(StopBookmarksActivity.this).lookupStopByStopCode((int) stopCode);
								if (busStop != null) {
									LocalDBHelper db = new LocalDBHelper(StopBookmarksActivity.this);
									try {
										db.addBookmark((int) busStop.getStopCode(), busStop.getStopName());
									} finally {
										db.close();
									}
									update();
								} else {
									new AlertDialog.Builder(StopBookmarksActivity.this)
										.setTitle("Invalid BusStop code")
										.setMessage("The code was invalid; please try again")
										.setPositiveButton(android.R.string.ok, null)
										.show();
								}
							}
						})
				.setNegativeButton(android.R.string.cancel, null)
				.show();
			return true;
		}

		return false;
	}
}